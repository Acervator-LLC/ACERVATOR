"""Drives `risk_tab.js` against `risk_tab_surface.py`.

WHAT IS PROVED
==============
The renderer module draws the Risk and Capital Management tab from the
`risk_tab.state` payload and holds no value of its own: no colour, no
title, no threshold. The gauge is drawn from the angles the surface
publishes, in the sixteenths of a degree Qt counts them in.

The bridge boundary is checked here too. `build_view_model` writes every
style sheet with Qt's alpha byte because a real widget paints from that
same dict; `view_model` publishes through `src.gui.color_alpha`, so the
share a browser reads leaves the surface and the renderer scales nothing.

FALSIFICATION
=============
Wrong if `payload_of` returned the same text whatever the surface holds,
when no comparison here could report. Every state is driven through the
real `view_model`, and
`test_the_bridge_keeps_the_qt_byte_out_of_the_published_payload` carries
its own control: the same colour is read off both functions and the two
readings must differ.
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
from src.gui.main_tabs import design_system_surface as dss
from src.gui.main_tabs import risk_tab_surface as surface
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
MODULE_PATH = WEB / "risk_tab.js"
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
READY_ROUNDS = 100
READY_STEP_MS = 100
PAGE_ATTEMPTS = 2
VIEW_SIZE_PX = (1400, 900)
HOST_WIDTH_PX = 1200
HOST_HEIGHT_PX = 800

#: The bridge method the module asks on, not a value it paints.
NAMED_METHOD = surface.METHOD

#: The tab shows an alert only while it is inside its window, so the
#: one alert driven here is stamped when this file is read.
ALERT_STAMP = time.time()

#: The one published string the module must also write. `arc` is the step
#: kind the gauge reads to tell a ring from a painted string.
ALLOWED_PAINTED = {"arc"}

MANAGER_SPEC: dict = {
    "status": {
        "drawdown_pct": 12.0,
        "peak_pnl": 412.5,
        "total_exposure": 1000.0,
        "critical_alerts": 0,
        "alerts_1h": 1,
        "rules": {
            "max_drawdown": {"threshold": 20.0, "action": "halt", "enabled": True},
            "max_exposure": {"threshold": 50.0, "action": "warn", "enabled": False},
        },
    },
    "snapshots": [
        {
            "running_count": 3,
            "total_exposure": 1000.0,
            "asset_exposures": {"BTC": 600.0, "ETH": 400.0},
            "exchange_exposures": {"coinbase": 700.0, "kraken": 300.0},
        }
    ],
    "alerts": [
        {
            "timestamp": ALERT_STAMP,
            "severity": "critical",
            "rule_name": "max_drawdown",
            "message": "drawdown past its ceiling",
            "action_taken": "halt",
        }
    ],
}

CRITICAL_SPEC: dict = {
    "status": {
        "drawdown_pct": 24.0,
        "peak_pnl": 0.0,
        "total_exposure": 100.0,
        "critical_alerts": 2,
        "alerts_1h": 2,
        "rules": {},
    },
    "snapshots": [
        {
            "running_count": 1,
            "total_exposure": 100.0,
            "asset_exposures": {"SOL": 100.0},
            "exchange_exposures": {"coinbase": 100.0},
        }
    ],
    "alerts": [],
}

STATE_PARAMS: dict = {
    "empty": {"reset": True},
    "painted": {"reset": True, "manager": MANAGER_SPEC, "action": "refresh"},
    "critical": {"reset": True, "manager": CRITICAL_SPEC, "action": "refresh"},
}
STATE_NAMES = tuple(sorted(STATE_PARAMS))


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

#: A whole turn, the unit the ring is given so a dash reads in degrees.
FULL_TURN = 360.0

#: How a division reads in the forty characters around a reported slash.
DIVIDES = " / "


def dash_fields(dash: Any) -> list:
    """One `stroke-dasharray` as the two numbers it carries."""
    return [float(one) for one in str(dash).split(",")]


class JsRuntime(JsEngine):
    """A QJSEngine holding `risk_tab.js` and a `window` global."""

    module_path = MODULE_PATH
    setter = "acervatorSetRiskTab"

    def named(self, call: str, *args: Any) -> Any:
        """Call one module method with JSON arguments and read its answer."""
        self.bind_json("ARGS", list(args))
        return self.json("acervatorRiskTab." + call + ".apply(null, JSON.parse(ARGS))")


@pytest.fixture()
def js(qapp) -> JsRuntime:
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_SOURCE)


# -- 1. the module holds what the surface published ---------------------


def test_the_module_publishes_the_bridge_method_the_surface_answers(js: JsRuntime):
    assert js.json("acervatorRiskTab.method") == surface.METHOD


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
    del payload["gauge_paint"]
    report = js.push(payload)
    assert {
        "where": None,
        "field": "gauge_paint",
        "fault": "missing",
        "detail": None,
    } in report["faults"]


def test_the_fault_list_reports_a_nested_field_the_payload_left_out(js: JsRuntime):
    payload = state_payload("painted")
    del payload["gauge"]["angle_unit"]
    report = js.push(payload)
    assert {
        "where": "gauge",
        "field": "angle_unit",
        "fault": "missing",
        "detail": None,
    } in report["faults"]


def test_the_module_refuses_a_payload_that_is_not_an_object(js: JsRuntime):
    report = js.push([])
    assert report["faults"] == [
        {"where": None, "field": None, "fault": "not-an-object", "detail": "object"}
    ]
    assert js.json("acervatorRiskTab.isLoaded()") is False


def test_the_module_counts_the_bars_and_rows_the_surface_grew(js: JsRuntime):
    payload = state_payload("painted")
    report = js.push(payload)
    assert report["held"]["bars"] == len(payload["asset_bars"]) + len(
        payload["exchange_bars"]
    )
    assert report["held"]["rows"] == len(payload["alert_rows"]) + len(
        payload["rule_rows"]
    )
    assert report["held"]["steps"] == len(payload["gauge_paint"]["steps"])


def test_an_empty_tab_carries_no_bar_and_no_row(js: JsRuntime):
    report = js.push(state_payload("empty"))
    assert report["held"]["bars"] == 0
    assert report["held"]["rows"] == 0


# -- 2. the module writes no value of its own ---------------------------


def test_the_module_writes_no_colour():
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"risk_tab.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_value_the_tab_paints():
    written = sorted(set(MODULE_LITERALS["strings"]) & PAINTED_VALUES)
    assert written == sorted(
        ALLOWED_PAINTED
    ), f"risk_tab.js spells out tab values: {written}"


def test_no_string_in_the_module_equals_a_design_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"risk_tab.js spells out token values: {written}"


def test_the_one_allowed_painted_string_is_the_step_kind_the_gauge_reads(
    js: JsRuntime,
):
    payload = state_payload("painted")
    js.push(payload)
    kinds = {step["kind"] for step in js.json("acervatorRiskTab.gaugeSteps()")}
    assert ALLOWED_PAINTED <= kinds, f"the gauge steps carry the kinds {sorted(kinds)}"


def test_the_module_writes_the_bridge_method_once():
    assert MODULE_LITERALS["strings"].count(NAMED_METHOD) == 1


def test_the_module_writes_no_threshold_the_surface_owns():
    limits = state_payload("painted")["bar"]
    owned = {
        str(limits[name])
        for name in (
            "asset_danger_pct",
            "asset_warning_pct",
            "exchange_danger_pct",
            "exchange_warning_pct",
        )
    }
    written = sorted(set(MODULE_LITERALS["numbers"]) & owned)
    assert not written, f"risk_tab.js spells out exposure thresholds: {written}"


def test_every_slash_the_module_writes_divides_two_values():
    """A regular-expression literal could hide a value the scan never reads.

    The gauge divides Qt sixteenths by their unit, so this module writes
    slashes a module carrying none would not. Each one must read as a
    division; a colour hidden inside a regular expression is caught by
    `test_the_module_writes_no_colour`, which scans the whole file.
    """
    stray = [
        context for context in MODULE_LITERALS["slashes"] if DIVIDES not in context
    ]
    assert not stray, f"risk_tab.js holds a slash that divides nothing: {stray}"


# -- 3. the gauge is drawn from the angles the surface published --------


def test_the_ring_reads_qt_sixteenths_of_a_degree_as_degrees(js: JsRuntime):
    payload = state_payload("painted")
    unit = payload["gauge"]["angle_unit"]
    track = payload["gauge_paint"]["steps"][0]
    assert js.named("degreesOf", track["span_angle"], unit) == (
        track["span_angle"] / unit
    )
    assert js.named("degreesOf", track["start_angle"], unit) == (
        track["start_angle"] / unit
    )


def test_the_ring_refuses_an_angle_unit_of_nothing(js: JsRuntime):
    assert js.named("degreesOf", 3600, 0) is None


def test_the_track_dash_covers_the_sweep_the_surface_asked_for(js: JsRuntime):
    payload = state_payload("painted")
    unit = payload["gauge"]["angle_unit"]
    span = abs(payload["gauge_paint"]["steps"][0]["span_angle"] / unit)
    assert dash_fields(js.named("ringDash", -span)) == [span, FULL_TURN - span]


def test_the_value_dash_is_the_track_dash_scaled_by_the_ratio(js: JsRuntime):
    payload = state_payload("painted")
    unit = payload["gauge"]["angle_unit"]
    steps = payload["gauge_paint"]["steps"]
    track = abs(steps[0]["span_angle"] / unit)
    sweep = abs(steps[1]["span_angle"] / unit)
    ratio = payload["gauge_paint"]["ratio"]
    assert sweep == pytest.approx(track * ratio, abs=1.0 / unit)
    drawn = dash_fields(js.named("ringDash", steps[1]["span_angle"] / unit))
    assert drawn == [sweep, FULL_TURN - sweep]


def test_the_ring_turns_by_the_negation_of_the_qt_start_angle(js: JsRuntime):
    payload = state_payload("painted")
    unit = payload["gauge"]["angle_unit"]
    start = payload["gauge_paint"]["steps"][0]["start_angle"] / unit
    assert js.named("ringRotation", start) == -start


def test_a_gauge_at_rest_draws_no_value_arc(js: JsRuntime):
    payload = state_payload("empty")
    steps = payload["gauge_paint"]["steps"]
    unit = payload["gauge"]["angle_unit"]
    assert steps[1]["span_angle"] == 0
    assert dash_fields(js.named("ringDash", steps[1]["span_angle"] / unit)) == [
        0.0,
        FULL_TURN,
    ]


def test_the_chunk_covers_the_share_of_its_track_the_bar_was_given(js: JsRuntime):
    payload = state_payload("painted")
    low, high = payload["bar"]["range"]
    bar = payload["asset_bars"][0]
    assert js.named("chunkShare", bar["asked_value"], low, high) == pytest.approx(
        (bar["asked_value"] - low) / (high - low)
    )


def test_the_chunk_refuses_a_track_with_no_span(js: JsRuntime):
    assert js.named("chunkShare", 50, 10, 10) is None


# -- 4. the colour boundary --------------------------------------------


#: A Qt alpha byte, well above the share a browser reads.
BYTE_ALPHA = 200


def test_the_bridge_keeps_the_qt_byte_out_of_the_published_payload():
    """`view_model` publishes the share; `build_view_model` keeps the byte."""
    tinted = f"color: {rgba(surface.ds.PRIMARY, BYTE_ALPHA)};"
    surface.view_model({"reset": True})
    surface.TAB_MODEL.status_style = tinted
    published_style = surface.view_model({})["status_style"]
    qt_style = surface.build_view_model(surface.TAB_MODEL)["status_style"]
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


def test_every_colour_the_two_tabs_paint_is_opaque_today():
    """No style either surface publishes carries an alpha field at all."""
    carried = sorted(
        value
        for value in PUBLISHED_VALUES
        if "rgba(" in value or (value.startswith("#") and len(value) > 7)
    )
    assert not carried, f"the risk tab now publishes transparency: {carried}"


# -- 5. the page draws what the surface published -----------------------


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
                if self.js("typeof window.acervatorSetRiskTab") == "function":
                    return
                self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the risk tab module: readyState "
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
        self.js("window.PAYLOAD = " + json.dumps(payload) + ";")
        self.js("window.acervatorSetRiskTab(window.PAYLOAD);")
        self.js("window.acervatorRiskTab.renderTab(window.HOST, window.PAYLOAD);")

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
        "window.partsOf('risk-tab').map(function (el) {"
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
        "window.partsOf('risk-group-title').map(function (el) {"
        "  return el.textContent; })"
    )
    assert titles == payload["group_titles"]


@pytest.mark.slow
def test_the_page_draws_one_metric_line_for_each_the_surface_published(
    browser: Browser,
):
    payload = state_payload("painted")
    browser.draw(payload)
    lines = browser.parsed(
        "window.partsOf('risk-metric').map(function (el) {"
        "  return el.textContent; })"
    )
    assert lines == [
        payload["status_text"],
        payload["peak_text"],
        payload["exposure_text"],
        payload["bots_text"],
    ]


@pytest.mark.slow
def test_the_page_paints_the_status_line_the_colour_the_surface_published(
    browser: Browser,
):
    payload = state_payload("critical")
    browser.draw(payload)
    painted = browser.parsed(
        "window.readStyle(window.partsOf('risk-metric')[0], ['color'])"
    )
    wanted = browser.js("window.probeColour(" + json.dumps(surface.ds.ERROR) + ")")
    assert payload["status_state"] == "critical"
    assert painted["color"] == wanted, (
        f"the status line paints {painted['color']} and the surface asked for "
        f"{wanted}"
    )


@pytest.mark.slow
def test_the_page_draws_one_bar_for_each_holding_the_surface_reported(
    browser: Browser,
):
    payload = state_payload("painted")
    browser.draw(payload)
    labels = browser.parsed(
        "window.partsOf('risk-bar-label').map(function (el) {"
        "  return el.textContent; })"
    )
    wanted = [bar["label"] for bar in payload["asset_bars"]] + [
        bar["label"] for bar in payload["exchange_bars"]
    ]
    assert labels == wanted


@pytest.mark.slow
def test_the_page_scales_each_chunk_to_the_share_its_bar_was_given(
    browser: Browser,
):
    payload = state_payload("painted")
    browser.draw(payload)
    low, high = payload["bar"]["range"]
    drawn = browser.parsed(
        "window.partsOf('risk-bar-chunk').map(function (el) {"
        "  return el.getBoundingClientRect().width; })"
    )
    tracks = browser.parsed(
        "window.partsOf('risk-bar-track').map(function (el) {"
        "  return el.getBoundingClientRect().width; })"
    )
    bars = payload["asset_bars"] + payload["exchange_bars"]
    assert len(drawn) == len(bars)
    for bar, chunk, track in zip(bars, drawn, tracks):
        share = (bar["asked_value"] - low) / (high - low)
        assert chunk == pytest.approx(track * share, rel=0.02), (
            f"{bar['label']} asked for {bar['asked_value']} of {high} and drew "
            f"{chunk} of {track}"
        )


@pytest.mark.slow
def test_the_page_draws_one_ring_for_the_track_and_one_for_the_reading(
    browser: Browser,
):
    payload = state_payload("painted")
    browser.draw(payload)
    unit = payload["gauge"]["angle_unit"]
    dashes = browser.parsed(
        "[window.partsOf('risk-gauge-track')[0].getAttribute('stroke-dasharray'),"
        " window.partsOf('risk-gauge-sweep')[0].getAttribute('stroke-dasharray')]"
    )
    steps = payload["gauge_paint"]["steps"]
    for dash, step in zip(dashes, steps):
        drawn = abs(step["span_angle"] / unit)
        assert dash_fields(dash) == [
            drawn,
            FULL_TURN - drawn,
        ], f"the ring drew {dash} for a span of {step['span_angle']} sixteenths"


@pytest.mark.slow
def test_the_page_draws_both_gauge_strings_the_surface_painted(browser: Browser):
    payload = state_payload("painted")
    browser.draw(payload)
    words = browser.parsed(
        "window.partsOf('risk-gauge-text').map(function (el) {"
        "  return el.textContent; })"
    )
    wanted = [
        step["text"]
        for step in payload["gauge_paint"]["steps"]
        if step["kind"] != "arc"
    ]
    assert words == wanted


@pytest.mark.slow
def test_the_page_draws_the_alert_table_the_surface_filled(browser: Browser):
    payload = state_payload("painted")
    browser.draw(payload)
    heads = browser.parsed(
        "Array.prototype.slice.call("
        "  window.HOST.querySelectorAll("
        '    \'[data-part="risk-alert-table"] [data-part="risk-head-cell"]\'))'
        "  .map(function (el) { return el.textContent; })"
    )
    cells = browser.parsed(
        "Array.prototype.slice.call("
        "  window.HOST.querySelectorAll("
        '    \'[data-part="risk-alert-table"] [data-part="risk-cell"]\'))'
        "  .map(function (el) { return el.textContent; })"
    )
    assert payload["alert_rows"], "the driven alert fell outside its window"
    assert heads == payload["alert_columns"]
    assert cells == [cell["text"] for row in payload["alert_rows"] for cell in row]


@pytest.mark.slow
def test_the_page_draws_the_rules_table_the_surface_filled(browser: Browser):
    payload = state_payload("painted")
    browser.draw(payload)
    cells = browser.parsed(
        "Array.prototype.slice.call("
        "  window.HOST.querySelectorAll("
        '    \'[data-part="risk-rule-table"] [data-part="risk-cell"]\'))'
        "  .map(function (el) { return el.textContent; })"
    )
    assert payload["rule_rows"], "the driven rules reached no row"
    assert cells == [cell["text"] for row in payload["rule_rows"] for cell in row]


@pytest.mark.slow
def test_the_page_paints_a_severity_cell_the_colour_the_surface_gave_it(
    browser: Browser,
):
    payload = state_payload("painted")
    browser.draw(payload)
    column = payload["severity_column"]
    painted = browser.parsed(
        "window.readStyle("
        "  window.HOST.querySelectorAll("
        '    \'[data-part="risk-alert-table"] [data-part="risk-row"]\')[1]'
        "    .querySelectorAll('[data-part=\"risk-cell\"]')[" + str(column) + "],"
        "  ['color'])"
    )
    wanted_value = payload["alert_rows"][0][column]["color"]
    wanted = browser.js("window.probeColour(" + json.dumps(wanted_value) + ")")
    assert wanted_value == payload["severity_critical_color"]
    assert painted["color"] == wanted


@pytest.mark.slow
def test_the_page_leaves_the_empty_tab_with_no_bar_and_no_row(browser: Browser):
    browser.draw(state_payload("empty"))
    assert browser.parsed("window.partsOf('risk-bar').length") == 0
    assert browser.parsed("window.partsOf('risk-cell').length") == 0


@pytest.mark.slow
def test_the_page_breaks_no_content_security_rule_drawing_the_tab(browser: Browser):
    browser.draw(state_payload("painted"))
    assert browser.parsed("window.VIOLATIONS") == []


# -- 6. the renderer runs the module ------------------------------------


def test_the_manifest_names_the_module_after_the_helpers_it_calls():
    order = load_order()
    assert runs_after(
        order, MODULE_PATH.name, "shared_widgets.js", "header_strip.js"
    ), f"risk_tab.js does not run after the helpers it calls: {order}"
