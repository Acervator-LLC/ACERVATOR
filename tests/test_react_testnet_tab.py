"""Drives `testnet_tab.js` against `testnet_tab_surface.py`.

The tab is served to the renderer over the ``testnet_tab.state`` bridge
method. These tests push a payload the real surface built and read back
what the module holds, then draw the same payload in the renderer page
and read the document it produced.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.color_alpha import css_colours
from src.gui.main_tabs import testnet_tab_surface as surface
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
MODULE_PATH = WEB / "testnet_tab.js"
HEADER_MODULE = WEB / "header_strip.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

API = "acervatorTestnetTab."
SETTER = "acervatorSetTestnetTab"

#: The closing line a whole module file ends with.
MODULE_TAIL = "})(window);"
MODULE_READ_ATTEMPTS = 200
#: A pause between reads, so retrying does not hold MODULE_PATH open
#: against the os.replace in another worker.
MODULE_READ_PAUSE_S = 0.01


def read_module() -> str:
    """Return MODULE_PATH text ending with MODULE_TAIL, retrying while not."""
    for _ in range(MODULE_READ_ATTEMPTS):
        found = MODULE_PATH.read_text(encoding="utf-8")
        if found.rstrip().endswith(MODULE_TAIL):
            return found
        time.sleep(MODULE_READ_PAUSE_S)
    raise AssertionError(MODULE_PATH.name + " never read back whole")


#: Read at collection, before any test body writes into the file.
MODULE_SOURCE = read_module()

JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 100
READY_STEP_MS = 100
PAGE_ATTEMPTS = 3
SETTLE_STEP_MS = 50
HOST_WIDTH_PX = 1200
HOST_HEIGHT_PX = 900

WALLET = "0x" + "c" * 38
OTHER_WALLET = "0x" + "e" * 38
TX_HASH = "0x" + "b" * 62
BLOCK_HASH = "0x" + "a" * 62
NOW_S = 3700.0

#: Each table is given a different number of rows and different text, so
#: one table's rows cannot be mistaken for another's.
CHAIN_STATE = {
    "chain": {
        "block_number": 3,
        "blocks": [
            {
                "number": 1,
                "block_hash": BLOCK_HASH,
                "parent_hash": "0x" + "0" * 62,
                "timestamp": 100.0,
                "transactions": [TX_HASH],
            },
            {
                "number": 2,
                "block_hash": "0x" + "f" * 62,
                "parent_hash": BLOCK_HASH,
                "timestamp": 200.0,
                "transactions": [],
            },
        ],
        "transactions": [
            {
                "tx_hash": TX_HASH,
                "block_number": 1,
                "from_addr": WALLET,
                "to_addr": OTHER_WALLET,
                "function_name": "adjudicate",
                "args": {"a": 1},
                "gas_used": 50000,
            }
        ],
        "events": [
            {
                "block_number": 1,
                "tx_hash": TX_HASH,
                "contract": "ACRV",
                "event_name": "Adjudicated",
                "args": {"a": 1, "b": 2, "c": 3, "d": 4},
            },
            {
                "block_number": 2,
                "tx_hash": TX_HASH,
                "contract": "ACRV",
                "event_name": "TokensMinted",
                "args": {"to": "x"},
            },
            {
                "block_number": 2,
                "tx_hash": TX_HASH,
                "contract": "ACRV",
                "event_name": "BotRegistered",
                "args": {},
            },
        ],
    },
    "balances": {WALLET: 5 * 10**18, OTHER_WALLET: 2 * 10**18},
    "mint_log": [{"recipient": WALLET, "tier": "Harvest"}],
    "stats": {
        "block_number": 3,
        "total_transactions": 7,
        "total_events": 9,
        "total_competitions": 2,
        "acrv_total_supply": 500000,
        "acrv_remaining": 9500000,
    },
}

#: The four table node names, each paired with the rows key it draws.
TABLE_PAIRS = (
    ("blocks_table", "blocks"),
    ("transactions_table", "transactions"),
    ("events_table", "events"),
    ("holders_table", "holders"),
)


def as_json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=True))


def payload() -> dict:
    """A real ``testnet_tab.state`` answer with all four tables filled."""
    return as_json(
        surface.view_model(
            {"reset": True, "state": CHAIN_STATE, "refresh": True, "now": NOW_S}
        )
    )


def logged_payload() -> dict:
    """A real payload carrying two lines the model's own log wrote."""
    model = surface.build_model(CHAIN_STATE)
    model.refresh_all(NOW_S)
    model.msg("first line", surface.CYAN, "01:02:03")
    model.chain_reset_message("a reason", "04:05:06")
    return as_json(css_colours(surface.build_view_model(model)))


class JsRuntime(JsEngine):
    """A QJSEngine running this module beside the shared style reader."""

    module_path = MODULE_PATH
    setter = SETTER

    def __init__(self, engine: Any, source: str, with_header: bool = True) -> None:
        super().__init__(engine, source)
        if with_header:
            loaded = engine.evaluate(
                HEADER_MODULE.read_text(encoding="utf-8"), HEADER_MODULE.name
            )
            assert not loaded.isError(), (
                HEADER_MODULE.name + " -> " + loaded.toString()
            )

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
def loaded(js: JsRuntime) -> JsRuntime:
    """The runtime after one real payload has been pushed into it."""
    js.push(payload())
    return js


# ---------------------------------------------------------------------
# What the module holds
# ---------------------------------------------------------------------


def test_the_module_defines_its_globals(js: JsRuntime):
    assert js.json("typeof " + API.rstrip(".")) == "object"
    assert js.json("typeof " + SETTER) == "function"
    assert js.json(API + "method") == surface.METHOD


def test_a_pushed_payload_is_held_whole(js: JsRuntime):
    given = payload()
    assert js.push(given) == {"loaded": True, "fault": None}
    assert js.json(API + "isLoaded()") is True
    assert js.json(API + "payload()") == given


def test_a_push_of_something_that_is_not_a_payload_is_refused(js: JsRuntime):
    """The positive control for the acceptance above."""
    assert js.push(["not", "a", "payload"]) == {
        "loaded": False,
        "fault": "not-an-object",
    }
    assert js.json(API + "isLoaded()") is False
    assert js.json(API + "payload()") is None


def test_forget_drops_the_payload_a_push_stored(loaded: JsRuntime):
    assert loaded.json(API + "isLoaded()") is True
    loaded.run(API + "forget()")
    assert loaded.json(API + "isLoaded()") is False
    assert loaded.json(API + "nodeNames()") == []


def test_the_module_names_every_node_the_surface_published(loaded: JsRuntime):
    assert loaded.json(API + "nodeNames()") == payload()["widget_names"]


def test_the_tree_reader_answers_the_published_children(loaded: JsRuntime):
    given = payload()
    assert loaded.called("childrenOf", "") == given["widget_children"][""]
    assert loaded.called("childrenOf", "tab") == given["widget_children"]["tab"]


def test_a_name_the_payload_never_carried_has_no_children(loaded: JsRuntime):
    """The positive control for the tree reader above."""
    assert loaded.called("childrenOf", "no_such_node") == []
    assert loaded.called("node", "no_such_node") is None


@pytest.mark.parametrize(("node_name", "rows_key"), TABLE_PAIRS)
def test_each_table_draws_the_rows_published_under_its_own_key(
    loaded: JsRuntime, node_name: str, rows_key: str
):
    given = payload()
    rows = given["rows"][rows_key]
    assert rows, f"the {rows_key} fixture is empty, so the comparison proves nothing"
    assert loaded.called("rowsKeyFor", node_name) == rows_key
    assert loaded.called("rowsFor", node_name) == rows


def test_the_four_tables_hold_four_different_row_sets(loaded: JsRuntime):
    """Two empty tables would compare equal and hide a crossed pairing."""
    seen = [loaded.called("rowsFor", name) for name, _ in TABLE_PAIRS]
    assert all(rows for rows in seen), seen
    written = [json.dumps(rows, sort_keys=True) for rows in seen]
    assert len(set(written)) == len(TABLE_PAIRS), written


@pytest.mark.parametrize(("node_name", "rows_key"), TABLE_PAIRS)
def test_each_table_carries_its_own_column_names(
    loaded: JsRuntime, node_name: str, rows_key: str
):
    assert loaded.called("columnsFor", node_name) == payload()["columns"][rows_key]


def test_a_node_that_is_no_table_names_no_rows_and_no_columns(loaded: JsRuntime):
    """The positive control for the two table readers above."""
    assert loaded.called("rowsFor", "log_view") == []
    assert loaded.called("columnsFor", "log_view") == []


def test_each_button_reports_the_action_the_surface_published(loaded: JsRuntime):
    actions = payload()["actions"]
    for node_name in ("run_button", "stress_button", "reset_button", "oracle_price"):
        found = loaded.called("actionFor", node_name)
        assert found is not None, node_name
        assert found in actions.values(), (node_name, found)
    assert loaded.called("actionFor", "run_button") == actions["run_button.clicked"]
    assert loaded.called("actionFor", "oracle_price") == (
        actions["oracle_price.valueChanged"]
    )


def test_a_node_the_actions_table_never_names_reports_no_action(loaded: JsRuntime):
    """The positive control for the action lookup above."""
    assert loaded.called("actionFor", "title") is None
    assert loaded.called("actionFor", "separator") is None
    assert loaded.called("actionFor", "blocks_table") is None


def test_the_timers_and_topics_are_the_ones_the_surface_published(loaded: JsRuntime):
    given = payload()
    assert loaded.json(API + "timers()") == given["timers"]
    assert loaded.json(API + "timerDelaysMs()") == given["timer_delays_ms"]
    assert loaded.json(API + "refreshIntervalMs()") == given["refresh_interval_ms"]
    assert loaded.json(API + "busTopics()") == given["bus_topics"]


def test_a_known_tier_and_a_known_event_read_their_own_colour(loaded: JsRuntime):
    given = payload()
    assert loaded.called("tierColour", "Harvest") == given["tier_colors"]["Harvest"]
    assert loaded.called("eventColour", "Adjudicated") == (
        given["event_colors"]["Adjudicated"]
    )


def test_an_unknown_tier_and_event_fall_back_to_the_published_colour(
    loaded: JsRuntime,
):
    given = payload()
    assert loaded.called("tierColour", "no such tier") == given["tier_fallback_color"]
    assert loaded.called("eventColour", "no such event") == (
        given["event_fallback_color"]
    )
    assert given["tier_fallback_color"] != given["tier_colors"]["Harvest"]


def test_a_log_line_splits_into_the_three_pieces_the_format_names(js: JsRuntime):
    given = logged_payload()
    assert given["log_lines"], "the log fixture is empty"
    js.push(given)
    first = js.called("logParts", given["log_lines"][0])
    assert first == {"stamp": "01:02:03", "color": surface.CYAN, "text": "first line"}
    second = js.called("logParts", given["log_lines"][1])
    assert second["color"] == surface.CHAIN_RESET_COLOR
    assert second["text"] == surface.CHAIN_RESET_MESSAGE.format(reason="a reason")


def test_a_line_that_is_not_in_the_published_format_splits_into_nothing(
    loaded: JsRuntime,
):
    """The positive control for the log splitter above."""
    assert loaded.called("logParts", "a plain line with no spans") is None
    assert loaded.called("logParts", "") is None


def test_the_style_reader_answers_the_declared_look_of_a_published_sheet(
    loaded: JsRuntime,
):
    found = loaded.called("styleOf", payload()["styles"]["section"])
    assert found["background"] == surface.PANEL
    assert found["borderRadius"] == "6px"


def test_the_style_reader_answers_nothing_for_a_sheet_with_no_declaration(
    loaded: JsRuntime,
):
    """The positive control for the style reader above."""
    assert loaded.called("styleOf", "") == {}


# ---------------------------------------------------------------------
# The module writes no value of its own
# ---------------------------------------------------------------------


def test_the_module_writes_no_number():
    """A numeric literal typed here has no publisher to compare it against."""
    found = js_literals(MODULE_SOURCE)["numbers"]
    assert not found, f"{MODULE_PATH.name} holds numeric literals: {found}"


def test_the_module_writes_no_colour():
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"{MODULE_PATH.name} holds colour literals: {found}"


def test_the_module_hides_no_value_behind_a_regular_expression():
    found = js_literals(MODULE_SOURCE)["slashes"]
    assert not found, (
        f"{MODULE_PATH.name} holds a slash outside a comment, which the"
        f" literal scan cannot read: {found}"
    )


def test_no_string_in_the_module_spells_out_a_value_the_tab_paints():
    painted = set(surface.SECTION_TITLES)
    painted.update(surface.STAT_KEYS)
    painted.update(surface.SYMBOLS)
    painted.add(surface.TAB_TITLE)
    painted.add(surface.NET_LABEL_TEXT)
    painted.update(
        [surface.RUN_BUTTON_TEXT, surface.STRESS_BUTTON_TEXT, surface.RESET_BUTTON_TEXT]
    )
    written = painted.intersection(js_literals(MODULE_SOURCE)["strings"])
    assert not written, f"{MODULE_PATH.name} spells out tab values: {written}"


WRITTEN_LINES = {
    "colour": 'var written = "#00ffcc";',
    "number": "var written = 12;",
    "regex": "var written = /ab+c/;",
    "painted": 'var written = "' + surface.TAB_TITLE + '";',
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
    if surface.TAB_TITLE in literals["strings"]:
        found.add("painted")
    return found


@pytest.mark.parametrize("kind", sorted(WRITTEN_LINES))
def test_the_literal_scan_names_one_written_line(kind: str):
    assert kind in caught_by_scan(WRITTEN_LINES[kind]), (
        f"the scan reported nothing on the {kind} line"
    )


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
            assert hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest() == before, (
                f"the file was not restored after the {kind} line"
            )
    finally:
        swap_module(MODULE_PATH, original)
    quiet = sorted(kind for kind, caught in caught_each.items() if kind not in caught)
    assert not quiet, f"the scan reported nothing on these lines in the file: {quiet}"
    assert hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest() == before


def test_the_renderer_runs_this_module_after_react_and_the_style_reader():
    order = load_order()
    assert runs_after(
        order,
        MODULE_PATH.name,
        "react.production.min.js",
        "react-dom.production.min.js",
        HEADER_MODULE.name,
    ), order


def test_the_order_reading_answers_no_for_the_two_the_other_way_round():
    """The positive control for the load-order reading above."""
    swapped = [MODULE_PATH.name, HEADER_MODULE.name]
    assert not runs_after(swapped, MODULE_PATH.name, HEADER_MODULE.name)
    assert not runs_after([HEADER_MODULE.name], MODULE_PATH.name, HEADER_MODULE.name)


# ---------------------------------------------------------------------
# What the renderer page draws
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
            "the page never defined the testnet tab module in "
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
    "window.SEEN = [];"
)


def draw(browser: Browser, model: dict) -> None:
    browser.js(PAGE_HELPERS)
    browser.js("window.MODEL = " + json.dumps(json.dumps(model)) + ";")
    browser.js(
        API
        + "renderTab(window.HOST, JSON.parse(window.MODEL), function (name, value) {"
        "  window.SEEN.push([name, value]);"
        "});"
    )


def count_of(browser: Browser, selector: str) -> int:
    return browser.parsed(
        "window.HOST.querySelectorAll(" + json.dumps(selector) + ").length"
    )


def test_the_tab_draws_one_element_for_every_node_the_surface_published(
    browser: Browser,
):
    given = payload()
    draw(browser, given)
    drawn = browser.parsed(
        "Array.prototype.map.call("
        "window.HOST.querySelectorAll('[data-node]'),"
        "function (one) { return one.getAttribute('data-node'); })"
    )
    assert sorted(set(drawn)) == sorted(set(given["widget_names"])), sorted(
        set(given["widget_names"]).symmetric_difference(drawn)
    )


def test_the_tab_carries_the_accessible_name_the_surface_declares(browser: Browser):
    draw(browser, payload())
    assert browser.parsed(
        "window.HOST.querySelector('[data-node=\"tab\"]').getAttribute('aria-label')"
    ) == surface.ACCESSIBLE_NAME


@pytest.mark.parametrize(("node_name", "rows_key"), TABLE_PAIRS)
def test_each_table_draws_a_row_for_every_row_the_surface_published(
    browser: Browser, node_name: str, rows_key: str
):
    given = payload()
    rows = given["rows"][rows_key]
    assert rows, f"the {rows_key} fixture is empty, so a zero count proves nothing"
    draw(browser, given)
    selector = '[data-node="' + node_name + '"] [data-part="row"]'
    assert count_of(browser, selector) == len(rows)
    drawn = browser.parsed(
        "Array.prototype.map.call("
        "window.HOST.querySelectorAll("
        + json.dumps(selector + ' [data-part="cell"]')
        + "), function (one) { return one.textContent; })"
    )
    assert drawn == [cell["text"] for row in rows for cell in row]


def test_the_four_tables_draw_four_different_row_counts_and_texts(browser: Browser):
    """Four equal tables would hide a table drawing another table's rows."""
    draw(browser, payload())
    seen = {}
    for node_name, rows_key in TABLE_PAIRS:
        seen[rows_key] = browser.parsed(
            "Array.prototype.map.call("
            "window.HOST.querySelectorAll("
            + json.dumps('[data-node="' + node_name + '"] [data-part="row"]')
            + "), function (one) { return one.textContent; })"
        )
    assert all(rows for rows in seen.values()), seen
    written = [json.dumps(rows) for rows in seen.values()]
    assert len(set(written)) == len(TABLE_PAIRS), seen


@pytest.mark.parametrize(("node_name", "rows_key"), TABLE_PAIRS)
def test_each_table_draws_its_own_column_headings(
    browser: Browser, node_name: str, rows_key: str
):
    given = payload()
    draw(browser, given)
    drawn = browser.parsed(
        "Array.prototype.map.call("
        "window.HOST.querySelectorAll("
        + json.dumps('[data-node="' + node_name + '"] [data-part="column"]')
        + "), function (one) { return one.textContent; })"
    )
    assert drawn == given["columns"][rows_key]


def test_a_cell_is_painted_the_colour_the_surface_gave_it(browser: Browser):
    """A colour reaches CSS as the surface published it, unscaled."""
    given = payload()
    draw(browser, given)
    wanted = given["rows"]["events"][0][1]["color"]
    assert wanted, "the event colour fixture is empty"
    found = browser.parsed(
        "window.getComputedStyle(window.HOST.querySelector("
        "'[data-node=\"events_table\"] [data-part=\"row\"][data-row=\"0\"]"
        " [data-part=\"cell\"][data-column=\"1\"]')).color"
    )
    assert found == rgb_of(wanted), found


def rgb_of(colour: str) -> str:
    """One ``#rrggbb`` colour as the ``rgb(r, g, b)`` a browser reports."""
    digits = colour.lstrip("#")
    channels = [int(digits[at : at + 2], 16) for at in range(0, 6, 2)]
    return "rgb(%d, %d, %d)" % tuple(channels)


def test_the_colour_reading_tells_two_different_real_cells_apart(browser: Browser):
    """The positive control for the painted-colour check above."""
    given = payload()
    draw(browser, given)
    first = browser.parsed(
        "window.getComputedStyle(window.HOST.querySelector("
        "'[data-node=\"events_table\"] [data-part=\"row\"][data-row=\"0\"]"
        " [data-part=\"cell\"][data-column=\"1\"]')).color"
    )
    second = browser.parsed(
        "window.getComputedStyle(window.HOST.querySelector("
        "'[data-node=\"events_table\"] [data-part=\"row\"][data-row=\"1\"]"
        " [data-part=\"cell\"][data-column=\"1\"]')).color"
    )
    assert given["rows"]["events"][0][1]["color"] != (
        given["rows"]["events"][1][1]["color"]
    )
    assert first != second, (first, second)


def test_a_button_click_reports_the_action_the_surface_named(browser: Browser):
    given = payload()
    draw(browser, given)
    browser.js("window.HOST.querySelector('[data-node=\"run_button\"]').click();")
    browser.settle(SETTLE_STEP_MS)
    assert browser.parsed("window.SEEN") == [
        [given["actions"]["run_button.clicked"], "run_button"]
    ]


def test_a_click_on_a_node_that_names_no_action_reports_nothing(browser: Browser):
    """The positive control for the click above."""
    draw(browser, payload())
    browser.js("window.HOST.querySelector('[data-node=\"title\"]').click();")
    browser.settle(SETTLE_STEP_MS)
    assert browser.parsed("window.SEEN") == []


def test_a_switched_off_button_draws_switched_off(browser: Browser):
    model = surface.build_model(CHAIN_STATE)
    model.run_enabled = False
    off = as_json(css_colours(surface.build_view_model(model)))
    draw(browser, off)
    assert browser.parsed(
        "window.HOST.querySelector('[data-node=\"run_button\"]').disabled"
    ) is True
    assert browser.parsed(
        "window.HOST.querySelector('[data-node=\"stress_button\"]').disabled"
    ) is False


def test_the_same_button_draws_switched_on_when_the_surface_says_so(
    browser: Browser,
):
    """The positive control for the switched-off button above."""
    given = payload()
    assert given["buttons_enabled"]["run_button"] is True
    draw(browser, given)
    assert browser.parsed(
        "window.HOST.querySelector('[data-node=\"run_button\"]').disabled"
    ) is False


def test_the_log_pane_draws_one_stamped_line_for_every_line_the_model_wrote(
    browser: Browser,
):
    given = logged_payload()
    assert len(given["log_lines"]) == 2, given["log_lines"]
    draw(browser, given)
    assert count_of(browser, '[data-node="log_view"] [data-part="log-line"]') == 2
    stamps = browser.parsed(
        "Array.prototype.map.call("
        "window.HOST.querySelectorAll('[data-part=\"log-stamp\"]'),"
        "function (one) { return one.textContent; })"
    )
    assert stamps == ["01:02:03", "04:05:06"]
    texts = browser.parsed(
        "Array.prototype.map.call("
        "window.HOST.querySelectorAll('[data-part=\"log-text\"]'),"
        "function (one) { return one.textContent; })"
    )
    assert texts[0] == "first line"


def test_an_empty_log_draws_no_line_at_all(browser: Browser):
    """The positive control for the log count above."""
    given = payload()
    assert given["log_lines"] == []
    draw(browser, given)
    assert count_of(browser, '[data-node="log_view"] [data-part="log-line"]') == 0


def test_the_run_controls_draw_the_ranges_the_surface_declares(browser: Browser):
    draw(browser, payload())
    assert browser.parsed(
        "window.HOST.querySelector('[data-node=\"bots_spin\"]').min"
    ) == str(surface.BOTS_MINIMUM)
    assert browser.parsed(
        "window.HOST.querySelector('[data-node=\"bots_spin\"]').max"
    ) == str(surface.BOTS_MAXIMUM)
    assert browser.parsed(
        "window.HOST.querySelector('[data-node=\"season_spin\"]').max"
    ) == str(surface.SEASON_MAXIMUM)
    drawn = browser.parsed(
        "Array.prototype.map.call("
        "window.HOST.querySelectorAll('[data-node=\"symbol_combo\"] option'),"
        "function (one) { return one.textContent; })"
    )
    assert drawn == list(surface.SYMBOLS)
