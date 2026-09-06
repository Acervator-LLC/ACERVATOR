"""The shell draws more than one converted panel, each addressed by name.

``desktop/renderer/panel_host.js`` takes the panel roster from the
generated manifest, draws each registered panel into its own host element
under ``#panels``, and writes the reason onto the page for a panel that
did not draw. ``PANEL_SURFACES`` names every module that registers; the
Console tab and the header strip are each compared against the Qt widget
they stand for, built from the shipped mixin and read at run time.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import bot_swarm_list_surface as swarm_list_surface
from src.gui.main_tabs import console_tab_surface as console_surface
from src.gui.main_tabs import design_system_surface as dss
from src.gui.main_tabs import header_strip_surface as header_surface
from src.gui.main_tabs import history_tab_surface as history_chrome_surface
from src.gui.main_tabs import market_inspector_tab_surface as inspector_surface
from src.gui.main_tabs import paper_trader_tab_surface as paper_surface
from src.gui.main_tabs import proof_of_accumulation_tab_surface as poa_surface
from src.gui.main_tabs import simulator_tab_surface as sim_surface
from src.gui.main_tabs import system_status_tab_surface as status_surface
from src.gui.main_tabs import trade_charts_tab_surface as charts_surface
from src.gui.main_tabs import trading_tab_surface as trading_surface
from tools import sync_renderer_modules as renderer_modules

RENDERER = REPO_ROOT / "desktop" / "renderer"
INDEX_HTML = RENDERER / "index.html"
MANIFEST_JS = RENDERER / "module_manifest.js"

CONSOLE_PANEL = "console_tab"
HEADER_PANEL = "header_strip"
SPARE_PANEL = "status_log"
ABSENT_PANEL = "no_such_panel"

#: Every module that calls ``register`` on the panel host, and the surface it
#: asks for its view model. A module joins by registering; adding one here
#: without that call fails the roster check below.
PANEL_SURFACES = {
    CONSOLE_PANEL: console_surface,
    HEADER_PANEL: header_surface,
    "bot_swarm_tab": swarm_list_surface,
    "history_tab": history_chrome_surface,
    "market_inspector_tab": inspector_surface,
    "paper_trader_tab": paper_surface,
    "proof_of_accumulation_tab": poa_surface,
    "simulator_tab": sim_surface,
    "system_status_tab": status_surface,
    "trade_charts_tab": charts_surface,
    "trading_tab": trading_surface,
}

REGISTERING_PANELS = sorted(PANEL_SURFACES)

JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 100
READY_STEP_MS = 100
PAGE_ATTEMPTS = 2
DRAW_ROUNDS = 100
DRAW_STEP_MS = 50

RECORDS = [
    {
        "name": "acervator.trading",
        "level": "INFO",
        "message": "scrum filled",
        "created": 1.0,
    },
    {
        "name": "acervator.risk",
        "level": "WARNING",
        "message": "fold armed",
        "created": 2.0,
    },
    {
        "name": "acervator.exchange",
        "level": "ERROR",
        "message": "order refused",
        "created": 3.0,
    },
]

STATS = {
    "total_scrummed_usd": 12345.678,
    "total_folded_usd": 987.65,
    "total_trades": 41,
    "running": 7,
    "total_errors_lifetime": 3,
    "total_realised_pnl": -12.5,
    "wallet_cash_usd": 500.25,
    "crypto_position_value_usd": 8100.5,
}

COUNTER_KEYS = ("scrummed", "folded", "trades", "bots", "errors")
COUNTER_LABEL = "strip/top-row/counter/label-row/counter-label"
COUNTER_VALUE = "strip/top-row/counter/counter-value"
LOG_BLOCK = "tab/splitter/log-pane/block"

THROWN = "the panel refuses to draw"


# -- the payloads both sides are driven from ---------------------------


def console_payload(records: list) -> dict:
    """The Console view model the bridge would serve for ``records``."""
    log_pane = console_surface.ConsolePane(console_surface.PANE_MAX_BLOCKS)
    signal_pane = console_surface.ConsolePane(console_surface.PANE_MAX_BLOCKS)
    model = console_surface.build_view_model(
        log_pane,
        signal_pane,
        console_surface.SignalLedger(),
        records=records,
    )
    return json.loads(json.dumps(model, ensure_ascii=True))


def header_payload() -> dict:
    """The header strip view model the bridge would serve for ``STATS``."""
    return json.loads(
        json.dumps(
            header_surface.view_model({"stats": STATS, "exchange_count": 3}),
            ensure_ascii=True,
        )
    )


def token_payload() -> dict:
    return json.loads(json.dumps(dss.view_model({}), ensure_ascii=True))


def manifest_panels() -> list:
    """Every panel name the generated manifest declares, in its order."""
    text = MANIFEST_JS.read_text(encoding="utf-8")
    return [name[: -len(".js")] for name in renderer_modules.manifest_entries(text)]


# -- the Qt widgets the panels stand for -------------------------------


def qt_available() -> Any:
    return pytest.importorskip("PySide6.QtWidgets")


def log_record(fields: dict) -> logging.LogRecord:
    """One record carrying the name, level, message and epoch given."""
    record = logging.LogRecord(
        name=fields["name"],
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg=fields["message"],
        args=(),
        exc_info=None,
    )
    record.levelname = fields["level"]
    record.created = float(fields["created"])
    return record


@pytest.fixture()
def qt_console(qapp):
    """The shipped Console tab, built by the mixin MainWindow uses.

    The mixin attaches its handler to the root logger and starts two
    timers, so both are put back before the next test runs.
    """
    widgets = qt_available()
    assert qapp is not None
    from src.gui.main_tabs.console_tab import ConsoleTabMixin

    class ConsoleTabWindow(ConsoleTabMixin, widgets.QWidget):
        def __init__(self, tabs) -> None:
            super().__init__()
            self.setAccessibleName("Console Tab Host")
            self._main_tabs = tabs
            self._build_console_tab()

        def _drain_signals(self) -> None:
            return None

        def _emit_console_health(self) -> None:
            return None

        def _refresh_console_pause_indicator(self) -> None:
            return None

        def _toggle_console_pause(self) -> None:
            return None

    root = logging.getLogger()
    named = logging.getLogger("acervator")
    kept = (list(root.handlers), root.level, list(named.handlers))
    tabs = widgets.QTabWidget()
    tab = ConsoleTabWindow(tabs)
    try:
        yield tab
    finally:
        tab._signal_timer.stop()
        tab._console_health_timer.stop()
        tab._console_pause_refresh.stop()
        root.handlers[:] = kept[0]
        root.setLevel(kept[1])
        named.handlers[:] = kept[2]
        tabs.deleteLater()


def qt_console_lines(tab, records: list) -> list:
    """Every line the Qt log pane holds after the records are handled."""
    for fields in records:
        tab._console_log_handler.handle(log_record(fields))
    return tab._console.toPlainText().splitlines()


@pytest.fixture()
def qt_header(qapp):
    """The shipped header strip, built by the mixin MainWindow uses."""
    widgets = qt_available()
    assert qapp is not None
    from src.gui.main_tabs.header_strip import HeaderStripMixin

    class HeaderStripWindow(HeaderStripMixin, widgets.QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setAccessibleName("Header Strip Host")
            self._build_header_strip()

        def _show_error_log_dialog(self) -> None:
            return None

        def _toggle_trading_mode(self) -> None:
            return None

        def _update_mode_btn_style(self) -> None:
            return None

    window = HeaderStripWindow()
    try:
        yield window
    finally:
        window.deleteLater()


def qt_counter_texts(window, values: dict) -> dict:
    """Each counter card's drawn strings, after it is given ``values``."""
    widgets = qt_available()
    cards = {
        "scrummed": window._stat_scrummed,
        "folded": window._stat_folded,
        "trades": window._stat_trades,
        "bots": window._stat_bots,
        "errors": window._stat_errors,
    }
    drawn = {}
    for key, card in cards.items():
        card.set_value(values[key])
        drawn[key] = [label.text() for label in card.findChildren(widgets.QLabel)]
    return drawn


# -- the page ----------------------------------------------------------


PAGE_HELPERS = (
    "window.readParts = function (root) {"
    "  var found = [];"
    "  var walk = function (el, path) {"
    "    var part = el.getAttribute('data-part');"
    "    var here = path;"
    "    if (part !== null) {"
    "      here = path ? path + '/' + part : part;"
    "      var own = '';"
    "      Array.prototype.slice.call(el.childNodes).forEach(function (n) {"
    "        if (n.nodeType === Node.TEXT_NODE) { own += n.nodeValue; } });"
    "      found.push({ path: here, text: own });"
    "    }"
    "    Array.prototype.slice.call(el.children).forEach(function (child) {"
    "      walk(child, here); });"
    "  };"
    "  if (root && root.firstChild) { walk(root.firstChild, ''); }"
    "  return found; };"
    "window.hostOf = function (name) {"
    "  return document.querySelector("
    "    '[data-panel=' + JSON.stringify(name) + ']'); };"
    "window.spareHost = function () {"
    "  var made = document.createElement('div');"
    "  document.body.appendChild(made);"
    "  window.SPARE = made;"
    "  return true; };"
)

FAKE_BRIDGE = (
    "window.acervator = { call: function (method) {"
    "  var answers = window.PANEL_MODELS || {};"
    "  if (!Object.prototype.hasOwnProperty.call(answers, method)) {"
    "    return Promise.reject(new Error('the backend has no ' + method));"
    "  }"
    "  return Promise.resolve(JSON.parse(JSON.stringify(answers[method])));"
    "} };"
)


class Browser:
    """Drives the real renderer page in the Chromium PySide6 ships."""

    def __init__(self) -> None:
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
        self.open_page()
        self.wait_for_host()
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

    def wait_for_host(self) -> None:
        for attempt in range(PAGE_ATTEMPTS):
            if attempt:
                self.open_page()
            for _ in range(READY_ROUNDS):
                if self.parsed("acervatorPanelHost.registered()") == REGISTERING_PANELS:
                    return
                self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never registered every panel: host "
            + str(self.js("typeof window.acervatorPanelHost"))
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


def give_tokens(browser: Browser) -> None:
    browser.js("window.TOKENS = " + json.dumps(json.dumps(token_payload())) + ";")
    written = browser.parsed(
        "(function () {"
        "  acervatorSetTokens(JSON.parse(window.TOKENS));"
        "  return acervatorTokens.apply(document.documentElement); })()"
    )
    assert written, "no design token reached the page's stylesheet"


def bind(browser: Browser, name: str, value: Any) -> None:
    browser.js(
        "window."
        + name
        + " = JSON.parse("
        + json.dumps(json.dumps(value, ensure_ascii=True))
        + ");"
    )


def mount(browser: Browser, panel: str, model: Any) -> bool:
    """Draw ``panel`` into a spare host and answer whether it drew."""
    bind(browser, "MODEL", model)
    browser.js("window.spareHost();")
    return browser.parsed(
        "acervatorPanelHost.mount("
        + json.dumps(panel)
        + ", window.SPARE, window.MODEL)"
    )


def spare_parts(browser: Browser) -> list:
    return browser.parsed("window.readParts(window.SPARE)")


def at_path(parts: list, path: str) -> list:
    return [one["text"] for one in parts if one["path"] == path]


def wait_for_hosts(browser: Browser, names: list) -> list:
    """Poll until every named host holds drawn markup, then report them."""
    for _ in range(DRAW_ROUNDS):
        drawn = browser.parsed(
            "(function () {"
            "  var found = [];"
            "  var hosts = document.querySelectorAll('#panels [data-panel]');"
            "  Array.prototype.slice.call(hosts).forEach(function (el) {"
            "    found.push({ name: el.getAttribute('data-panel'),"
            "      children: el.children.length }); });"
            "  return found; })()"
        )
        got = [one["name"] for one in drawn if one["children"]]
        if all(name in got for name in names):
            return drawn
        browser.settle(DRAW_STEP_MS)
    raise AssertionError(
        "the shell never drew "
        + ", ".join(names)
        + "; faults: "
        + str(browser.parsed("acervatorPanelHost.faults()"))
    )


# -- the roster ---------------------------------------------------------


def test_the_panel_roster_is_the_generated_manifest(browser: Browser):
    """The shell holds no list of panels. Every name it can address is a
    module name ``tools/sync_renderer_modules.py`` wrote."""
    declared = manifest_panels()
    assert len(declared) > 60, f"the manifest declared only {len(declared)} modules"
    assert browser.parsed("acervatorPanelHost.names()") == declared


def test_the_registered_panels_are_the_modules_that_asked_for_a_host(
    browser: Browser,
):
    """A module joins the roster by registering from its own script tag,
    and the host reads the name off that tag."""
    assert browser.parsed("acervatorPanelHost.registered()") == REGISTERING_PANELS
    declared = manifest_panels()
    assert browser.parsed("acervatorPanelHost.wanted()") == [
        name for name in declared if name in PANEL_SURFACES
    ]


# -- the shell draws both ----------------------------------------------


def panel_models() -> dict:
    """One view model per registering panel, keyed by its bridge method."""
    answers = {
        console_surface.METHOD: console_payload(RECORDS),
        header_surface.METHOD: header_payload(),
    }
    for name, source in PANEL_SURFACES.items():
        if name not in (CONSOLE_PANEL, HEADER_PANEL):
            answers[source.METHOD] = source.view_model({})
    return answers


def test_the_shell_draws_every_registered_panel_into_its_own_host(
    browser: Browser,
):
    """The whole claim of this unit: one page, many panels, each addressed
    by its own name and drawn into its own element."""
    give_tokens(browser)
    bind(browser, "PANEL_MODELS", panel_models())
    browser.js(FAKE_BRIDGE)
    browser.js("acervatorMountPanels();")
    wanted = browser.parsed("acervatorPanelHost.wanted()")
    drawn = wait_for_hosts(browser, wanted)
    assert [one["name"] for one in drawn] == wanted
    assert browser.parsed("acervatorPanelHost.faults()") == []
    lines = browser.parsed(
        "window.readParts(window.hostOf(" + json.dumps(CONSOLE_PANEL) + "))"
    )
    assert at_path(lines, LOG_BLOCK) == console_payload(RECORDS)["log_pane"]["blocks"]
    counters = browser.parsed(
        "window.readParts(window.hostOf(" + json.dumps(HEADER_PANEL) + "))"
    )
    assert at_path(counters, COUNTER_LABEL) == [
        card["label"] for card in header_payload()["counters"]
    ]


# -- a panel that does not draw says so --------------------------------


def test_a_panel_name_the_manifest_never_names_is_reported_on_the_page(
    browser: Browser,
):
    """The reason lands in the host element and in the fault list, so a
    panel that did not draw is never a blank rectangle."""
    assert mount(browser, ABSENT_PANEL, None) is False
    shown = browser.js("window.SPARE.textContent")
    assert ABSENT_PANEL in shown, shown
    assert "manifest" in shown, shown
    reason = "the manifest names no " + ABSENT_PANEL + ".js"
    assert browser.js("window.SPARE.getAttribute('data-panel-error')") == reason
    assert browser.parsed("acervatorPanelHost.faults()") == [
        {"panel": ABSENT_PANEL, "reason": reason}
    ]
    assert (
        browser.js("document.documentElement.getAttribute('data-panel-error')")
        == ABSENT_PANEL
    )


def test_a_panel_the_manifest_names_draws_and_records_no_fault(browser: Browser):
    """The control for the check above. A host that reported every panel
    as faulty would say nothing about the one that is missing."""
    give_tokens(browser)
    assert mount(browser, CONSOLE_PANEL, console_payload(RECORDS)) is True
    assert browser.parsed("acervatorPanelHost.faults()") == []
    assert browser.parsed("window.SPARE.hasAttribute('data-panel-error')") is False
    assert (
        browser.parsed("document.documentElement.hasAttribute('data-panel-error')")
        is False
    )


def test_a_panel_that_throws_while_drawing_names_the_panel_and_the_error(
    browser: Browser,
):
    """The error reaches the page. A swallowed catch would leave the host
    empty and the operator with no reason."""
    browser.js(
        "acervatorPanelHost.register({ render: function () {"
        "  throw new Error("
        + json.dumps(THROWN)
        + "); } }, "
        + json.dumps(SPARE_PANEL)
        + ");"
    )
    assert mount(browser, SPARE_PANEL, None) is False
    shown = browser.js("window.SPARE.textContent")
    assert SPARE_PANEL in shown, shown
    assert THROWN in shown, shown
    assert browser.parsed("acervatorPanelHost.faults()") == [
        {
            "panel": SPARE_PANEL,
            "reason": "the panel threw while drawing: " + THROWN,
        }
    ]


def test_a_registered_panel_that_draws_leaves_no_error_text(browser: Browser):
    """The control for the check above, run through the same registration
    with a render that returns rather than throws."""
    browser.js(
        "acervatorPanelHost.register({ render: function (target) {"
        "  target.textContent = "
        + json.dumps(THROWN)
        + "; } }, "
        + json.dumps(SPARE_PANEL)
        + ");"
    )
    assert mount(browser, SPARE_PANEL, None) is True
    assert browser.js("window.SPARE.textContent") == THROWN
    assert browser.parsed("acervatorPanelHost.faults()") == []


def test_a_backend_that_refuses_the_view_model_is_named_on_the_panel(
    browser: Browser,
):
    """The promise's rejection is handled where the panel is drawn, so the
    refusal is on screen rather than dropped into a dead catch."""
    bind(browser, "PANEL_MODELS", {})
    browser.js(FAKE_BRIDGE)
    browser.js("window.spareHost();")
    browser.js(
        "acervatorPanelHost.open(" + json.dumps(CONSOLE_PANEL) + ", window.SPARE);"
    )
    for _ in range(DRAW_ROUNDS):
        if browser.parsed("acervatorPanelHost.faults()"):
            break
        browser.settle(DRAW_STEP_MS)
    shown = browser.js("window.SPARE.textContent")
    assert CONSOLE_PANEL in shown, shown
    assert console_surface.METHOD in shown, shown
    assert [one["panel"] for one in browser.parsed("acervatorPanelHost.faults()")] == [
        CONSOLE_PANEL
    ]


def test_a_backend_that_answers_leaves_the_panel_without_a_fault(browser: Browser):
    """The control for the check above, run against a bridge that answers."""
    give_tokens(browser)
    bind(browser, "PANEL_MODELS", {console_surface.METHOD: console_payload(RECORDS)})
    browser.js(FAKE_BRIDGE)
    browser.js("window.spareHost();")
    browser.js(
        "acervatorPanelHost.open(" + json.dumps(CONSOLE_PANEL) + ", window.SPARE);"
    )
    for _ in range(DRAW_ROUNDS):
        if browser.js("window.SPARE.children.length"):
            break
        browser.settle(DRAW_STEP_MS)
    assert browser.parsed("acervatorPanelHost.faults()") == []
    assert at_path(spare_parts(browser), LOG_BLOCK) == (
        console_payload(RECORDS)["log_pane"]["blocks"]
    )


# -- the drawn panel against the Qt widget it stands for ----------------


def test_the_mounted_console_panel_draws_the_lines_the_qt_pane_draws(
    browser: Browser, qt_console
):
    """The React Console, drawn through the shell's own mount, against the
    QPlainTextEdit the shipped tab paints from the same records."""
    give_tokens(browser)
    painted = qt_console_lines(qt_console, RECORDS)
    assert len(painted) == len(RECORDS), f"the Qt pane painted {painted}"
    assert mount(browser, CONSOLE_PANEL, console_payload(RECORDS)) is True
    drawn = at_path(spare_parts(browser), LOG_BLOCK)
    assert drawn == painted, f"React drew {drawn}, Qt painted {painted}"


def test_the_console_line_check_names_a_line_the_two_sides_do_not_share(
    browser: Browser, qt_console
):
    """The control. A comparison blind to the text would report agreement
    on a line only one side shows."""
    give_tokens(browser)
    painted = qt_console_lines(qt_console, RECORDS)
    changed = [dict(one) for one in RECORDS]
    changed[1]["message"] = changed[1]["message"] + "!"
    assert mount(browser, CONSOLE_PANEL, console_payload(changed)) is True
    drawn = at_path(spare_parts(browser), LOG_BLOCK)
    differing = [at for at, line in enumerate(painted) if drawn[at] != line]
    assert differing == [1], f"the check named {differing}"


def test_the_mounted_header_panel_draws_the_counter_text_the_qt_cards_draw(
    browser: Browser, qt_header
):
    """The React header strip, drawn through the shell's own mount, against
    the five StatCard widgets the shipped mixin builds."""
    give_tokens(browser)
    payload = header_payload()
    values = {card["key"]: card["text"] for card in payload["counters"]}
    painted = qt_counter_texts(qt_header, values)
    assert sorted(painted) == sorted(COUNTER_KEYS), f"the Qt strip built {painted}"
    assert mount(browser, HEADER_PANEL, payload) is True
    parts = spare_parts(browser)
    labels = at_path(parts, COUNTER_LABEL)
    texts = at_path(parts, COUNTER_VALUE)
    assert len(labels) == len(COUNTER_KEYS), f"React drew {labels}"
    for at, card in enumerate(payload["counters"]):
        shown = painted[card["key"]]
        assert labels[at] in shown, f"{card['key']}: Qt drew {shown}"
        assert texts[at] in shown, f"{card['key']}: Qt drew {shown}"


def test_the_header_counter_check_names_a_counter_the_two_sides_do_not_share(
    browser: Browser, qt_header
):
    """The control. A comparison blind to the figure would report agreement
    on a counter only one side shows."""
    give_tokens(browser)
    payload = header_payload()
    values = {card["key"]: card["text"] for card in payload["counters"]}
    painted = qt_counter_texts(qt_header, values)
    payload["counters"][0]["text"] = payload["counters"][0]["text"] + "0"
    assert mount(browser, HEADER_PANEL, payload) is True
    texts = at_path(spare_parts(browser), COUNTER_VALUE)
    differing = [
        at
        for at, card in enumerate(payload["counters"])
        if texts[at] not in painted[card["key"]]
    ]
    assert differing == [0], f"the check named {differing}"


# -- the tab bar --------------------------------------------------------


def tab_names(browser: Browser) -> list:
    """Every tab the bar drew, in document order."""
    return browser.parsed(
        "(function () {"
        "  var found = [];"
        "  var bar = document.getElementById('tabs');"
        "  Array.prototype.slice.call("
        "    bar.querySelectorAll('[data-tab]')).forEach(function (el) {"
        "    found.push(el.getAttribute('data-tab')); });"
        "  return found; })()"
    )


def build_tabs(browser: Browser) -> list:
    """Answer a bridge, build the bar, and report the tabs it drew."""
    give_tokens(browser)
    bind(browser, "PANEL_MODELS", panel_models())
    browser.js(FAKE_BRIDGE)
    return browser.parsed("acervatorBuildTabs()")


def wait_for_children(browser: Browser, name: str) -> int:
    """Poll until the named host holds markup, then report how much."""
    for _ in range(DRAW_ROUNDS):
        held = browser.js(
            "(function () { var el = window.hostOf("
            + json.dumps(name)
            + "); return el === null ? 0 : el.children.length; })()"
        )
        if held:
            return held
        browser.settle(DRAW_STEP_MS)
    raise AssertionError(
        name
        + " never drew; faults: "
        + str(browser.parsed("acervatorPanelHost.faults()"))
    )


def test_the_tab_bar_holds_one_tab_for_every_registered_panel(browser: Browser):
    """``tab_names`` equals ``acervatorPanelHost.wanted()``. The tab set is
    ``REGISTERING_PANELS``, the modules that registered."""
    drawn = build_tabs(browser)
    assert drawn == browser.parsed("acervatorPanelHost.wanted()")
    assert tab_names(browser) == drawn
    assert sorted(drawn) == REGISTERING_PANELS, f"the bar drew {drawn}"


def test_the_tab_bar_gives_no_tab_to_a_module_that_registered_no_panel(
    browser: Browser,
):
    """``SPARE_PANEL`` is in ``manifest_panels`` and in no ``tab_names``
    entry until something registers it."""
    build_tabs(browser)
    assert SPARE_PANEL in manifest_panels()
    assert SPARE_PANEL not in tab_names(browser)


def test_a_module_that_registers_a_panel_gains_a_tab(browser: Browser):
    """The control for the check above. ``SPARE_PANEL`` gains a tab once it
    registers with ``acervatorPanelHost``."""
    browser.js(
        "acervatorPanelHost.register({ render: function (target) {"
        "  target.textContent = "
        + json.dumps(THROWN)
        + "; } }, "
        + json.dumps(SPARE_PANEL)
        + ");"
    )
    drawn = build_tabs(browser)
    assert SPARE_PANEL in drawn
    assert SPARE_PANEL in tab_names(browser)


def test_selecting_a_tab_leaves_exactly_one_panel_showing(browser: Browser):
    """The whole claim of the bar: one panel on screen, and it is the one
    whose tab is selected."""
    drawn = build_tabs(browser)
    assert browser.parsed("acervatorTabBar.visible()") == [drawn[0]]
    other = drawn[-1]
    browser.js("acervatorTabBar.select(" + json.dumps(other) + ");")
    assert browser.parsed("acervatorTabBar.visible()") == [other]
    assert browser.js("acervatorTabBar.selected()") == other


def test_clicking_a_tab_button_shows_that_panel(browser: Browser):
    """A click on the ``data-tab`` button drives ``acervatorTabBar.visible``
    and sets ``data-selected`` on that button."""
    drawn = build_tabs(browser)
    other = drawn[-1]
    picker = "document.querySelector('[data-tab=' + " + json.dumps(json.dumps(other))
    browser.js(picker + " + ']').click();")
    assert browser.parsed("acervatorTabBar.visible()") == [other]
    assert browser.js(picker + " + ']').getAttribute('data-selected')") == "true"


def test_the_selected_tab_draws_its_own_panel_and_records_no_fault(browser: Browser):
    """A tab that shows an empty rectangle is not a screen. The selected
    panel holds drawn markup and ``acervatorPanelHost.faults`` stays empty."""
    build_tabs(browser)
    browser.js("acervatorTabBar.select(" + json.dumps(CONSOLE_PANEL) + ");")
    assert wait_for_children(browser, CONSOLE_PANEL) > 0
    lines = browser.parsed(
        "window.readParts(window.hostOf(" + json.dumps(CONSOLE_PANEL) + "))"
    )
    assert at_path(lines, LOG_BLOCK) == console_payload(RECORDS)["log_pane"]["blocks"]
    assert browser.parsed("acervatorPanelHost.faults()") == []


def test_a_tab_label_drops_the_module_suffix_and_capitalises_each_word(
    browser: Browser,
):
    """``acervatorTabBar.label`` derives the tab text from the module name,
    so a module that lands carries its own label."""
    assert browser.js("acervatorTabBar.label('proof_of_accumulation_tab')") == (
        "Proof Of Accumulation"
    )
    assert browser.js("acervatorTabBar.label('header_strip')") == "Header Strip"
    assert browser.js("acervatorTabBar.label('trading_tab')") == "Trading"
