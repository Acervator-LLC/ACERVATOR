"""The React Indicator Voting Panel, against the surface that describes it.

WHAT IS PROVED
==============
``src/gui/web/indicator_panel.js`` draws the panel that
``src/gui/main_tabs/indicator_panel_surface.py`` describes, and carries no
colour, size or text of its own.

COLOUR IS THE POINT
===================
Qt reads an alpha as a 0-255 byte and CSS reads it as a 0-1 fraction. The
module converts every alpha through the payload's own ``alpha_unit`` and
never copies a Qt style sheet into CSS. Each colour test names the byte
the surface published and the fraction the page painted, and the control
is a byte handed straight to CSS: a page that did that would report the
alpha clamped to 1.

TIMERS ARE NEVER TIMED
======================
Chromium throttles timers in an offscreen view, so nothing here asserts
elapsed time. The frame interval is read as a published value and the
animation is advanced frame by frame.

HOW THE JAVASCRIPT IS RUN
=========================
Node is not installed and nothing here adds a JavaScript test runner.
``QJSEngine`` from ``PySide6.QtQml`` runs the module as plain JavaScript
and answers in JSON. ``QWebEngineView`` loads the real
``desktop/renderer/index.html`` from disk, which is the only way to draw
the panel with the vendored React under the page's own policy.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import indicator_panel_surface as surface
from tests.fixtures.web_js_modules import HEX_COLOUR, JsEngine, js_literals, new_engine

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "indicator_panel.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: Read at collection, before any test body touches the file.
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")
MODULE_LITERALS = js_literals(MODULE_SOURCE)

JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 100
READY_STEP_MS = 100
PAGE_ATTEMPTS = 2

ALPHA_SCALE = 255.0

BULLISH = "BULLISH"
BEARISH = "BEARISH"
NEUTRAL = "NEUTRAL"


def signal(indicator: str, direction: str, confidence: float, **details) -> dict:
    return {
        "indicator": indicator,
        "direction": direction,
        "confidence": confidence,
        "details": dict(details),
    }


def parts_of(colour: str) -> list:
    """The four numbers inside one ``rgba(...)`` value."""
    body = str(colour).split("(")[-1].split(")")[0]
    return [float(one.strip()) for one in body.split(",")]


def channels_of(colour: str) -> list:
    """The red, green and blue of one ``rgba(...)`` value, as whole numbers."""
    return [int(one) for one in parts_of(colour)[:3]]


def alpha_fraction(colour: str) -> float:
    """The 0-1 alpha CSS reads out of one ``rgba(...)`` value."""
    return parts_of(colour)[-1]


LIVE_SUMMARY = {
    "5m": {
        "bullish": 4,
        "bearish": 2,
        "neutral": 6,
        "net_score": 1.25,
        "confidence": 0.72,
        "composite_net": 1.9,
        "signals": [
            signal("bollinger_bands", BULLISH, 0.8),
            signal("vortex", BEARISH, 0.55),
            signal("adx", BULLISH, 0.4, adx=27.4, ranging=False),
            signal("rsi", NEUTRAL, 0.05),
        ],
        "locks": [],
    },
    "1h": {
        "bullish": 3,
        "bearish": 1,
        "neutral": 8,
        "net_score": -0.5,
        "confidence": 0.2,
        "signals": [signal("macd", BEARISH, 0.66)],
        "locks": [
            {"source_tf": "4h", "locked_direction": "SELL", "candles_remaining": 2}
        ],
    },
}


def bridge_payload(**params) -> dict:
    """One payload straight from the surface, exactly as the bridge answers."""
    surface.view_model({"reset": True})
    surface.view_model(
        {"action": "set_bots",
         "bots": [
             {
                 "bot_id": "aaaa11112222",
                 "symbol": "BTC-USD",
                 "mode": "accumulation",
                 "state": "running",
             }
         ]}
    )
    surface.view_model({"action": "set_rates", "snapshot": {
        "btc_usd": 60000.0,
        "eth_usd": 3000.0,
        "sat_per_dollar": 1666.0,
        "sat_per_cent": 16.0,
        "gwei_per_dollar": 333333.0,
        "gwei_per_cent": 3333.0,
        "source": "coinbase",
    }})
    for action, body in params.items():
        surface.view_model(dict(body, action=action))
    return surface.view_model({})


class JsRuntime(JsEngine):
    """A QJSEngine holding ``indicator_panel.js`` and a ``window`` global."""

    module_path = MODULE_PATH
    setter = "acervatorSetIndicatorPanel"

    def api(self, expression: str) -> Any:
        return self.json("window.acervatorIndicatorPanel." + expression)


@pytest.fixture()
def js(qapp) -> JsRuntime:
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_SOURCE)


# -- 1. the module carries none of the panel's values ------------------


def test_the_module_writes_no_colour_of_its_own() -> None:
    found = [one for one in MODULE_LITERALS["strings"] if HEX_COLOUR.fullmatch(one)]
    assert not found, (
        "indicator_panel.js must paint the surface's colours, never its own; "
        f"found {found}"
    )


def test_the_module_hides_no_value_behind_a_regular_expression() -> None:
    assert not MODULE_LITERALS["slashes"], (
        "a regular-expression literal could hide a value the scan never reads; "
        f"found {MODULE_LITERALS['slashes']}"
    )


def test_the_literal_scan_would_report_a_colour_if_one_were_there() -> None:
    """The positive control for the two scans above."""
    planted = js_literals('var accent = "#00ff88";\nvar re = /x/;')
    assert any(HEX_COLOUR.fullmatch(one) for one in planted["strings"])
    assert planted["slashes"], "the scan must report a stray slash"


def test_the_module_declares_every_field_the_surface_publishes(js: JsRuntime) -> None:
    payload = bridge_payload()
    declared = set(js.api("declaredFields()"))
    published = set(payload.keys())
    assert declared == published, (
        "the module's declared fields and the payload must agree; "
        f"only in payload {sorted(published - declared)}, "
        f"only in module {sorted(declared - published)}"
    )


def test_a_payload_with_every_field_raises_no_fault(js: JsRuntime) -> None:
    report = js.push(bridge_payload())
    assert report["faults"] == [], f"faults: {report['faults']}"


def test_a_payload_missing_a_field_is_named_rather_than_drawn(js: JsRuntime) -> None:
    """The positive control for the field check."""
    payload = bridge_payload()
    payload.pop("staleness")
    report = js.push(payload)
    assert any(one["where"] == "staleness" for one in report["faults"]), (
        f"faults: {report['faults']}"
    )


def test_a_payload_that_is_not_an_object_is_refused(js: JsRuntime) -> None:
    report = js.push("not a panel")
    assert report["held"] is None
    assert report["faults"], "a refusal must say why"


# -- 2. the alpha byte becomes a CSS fraction --------------------------


def test_a_qt_alpha_byte_is_scaled_by_the_published_unit(js: JsRuntime) -> None:
    payload = bridge_payload()
    js.push(payload)
    byte = payload["staleness"]["background_alpha"]
    js.bind_json("BYTE", byte)
    got = js.json("window.acervatorIndicatorPanel.cssAlpha(" + json.dumps(payload) + ", JSON.parse(BYTE))")
    assert got == pytest.approx(byte / ALPHA_SCALE), (
        f"Qt alpha byte {byte} must reach CSS as {byte / ALPHA_SCALE}, got {got}"
    )


def test_a_converted_alpha_always_lands_inside_the_css_range(js: JsRuntime) -> None:
    payload = bridge_payload()
    js.push(payload)
    for byte in (0, 12, 90, 120, 200, 255):
        js.bind_json("BYTE", byte)
        got = js.json(
            "window.acervatorIndicatorPanel.cssAlpha("
            + json.dumps(payload)
            + ", JSON.parse(BYTE))"
        )
        assert 0.0 <= got <= 1.0, (
            f"byte {byte} converted to {got}, which CSS would clamp"
        )


def test_the_raw_qt_byte_would_leave_the_css_range(js: JsRuntime) -> None:
    """The control. A byte handed to CSS unconverted is the shipped defect."""
    byte = surface.STALENESS_BACKGROUND_ALPHA
    assert byte > 1.0, (
        f"alpha byte {byte} read as a CSS fraction would clamp to fully opaque, "
        "which is exactly what conversion prevents"
    )


def test_the_staleness_banner_is_painted_as_a_translucent_wash(js: JsRuntime) -> None:
    payload = bridge_payload()
    js.push(payload)
    band = payload["staleness"]
    js.bind_json("MODEL", payload)
    painted_colour = js.json(
        "window.acervatorIndicatorPanel.rgba(JSON.parse(MODEL), "
        + json.dumps(band["background_rgb"])
        + ", "
        + str(band["background_alpha"])
        + ")"
    )
    assert channels_of(painted_colour) == band["background_rgb"], (
        f"the banner keeps its own hue; got {painted_colour}"
    )
    assert 0.0 < alpha_fraction(painted_colour) < 1.0, (
        "CSS must receive a fraction, not Qt's byte; "
        f"got {painted_colour} for byte {band['background_alpha']}"
    )
    painted_byte = alpha_fraction(painted_colour) * ALPHA_SCALE
    assert painted_byte == pytest.approx(band["background_alpha"]), (
        f"scaled back up the painted alpha must be the byte Qt published; "
        f"got {painted_byte} against {band['background_alpha']}"
    )


def test_a_cell_tint_is_painted_at_the_cell_s_own_converted_alpha(
    js: JsRuntime,
) -> None:
    payload = bridge_payload(set_summary={"summary": LIVE_SUMMARY, "symbol": "BTC-USD"})
    js.push(payload)
    fills = js.api("cellFills(0)")
    cell = payload["tables"][0]["rows"][0]["cells"][1]
    painted_colour = fills[0][1]
    assert channels_of(painted_colour) == cell["fill_rgb"], (
        f"the tint keeps the cell's hue; got {painted_colour}"
    )
    assert 0.0 < alpha_fraction(painted_colour) < 1.0, (
        f"a cell tint is a wash; got {painted_colour}"
    )
    painted_byte = alpha_fraction(painted_colour) * ALPHA_SCALE
    assert painted_byte == pytest.approx(cell["fill_alpha"]), (
        f"the cell's own alpha byte {cell['fill_alpha']} must reach the page; "
        f"got {painted_byte} from {painted_colour}"
    )


def test_an_alpha_outside_the_qt_byte_range_is_named(js: JsRuntime) -> None:
    """The positive control for the alpha check."""
    payload = bridge_payload()
    payload["staleness"]["background_alpha"] = 900
    report = js.push(payload)
    assert any(one["where"] == "staleness" for one in report["faults"]), (
        f"faults: {report['faults']}"
    )


# -- 3. the rows the panel draws ---------------------------------------


def test_each_table_draws_one_row_per_timeframe(js: JsRuntime) -> None:
    js.push(bridge_payload(set_summary={"summary": LIVE_SUMMARY, "symbol": "BTC-USD"}))
    assert js.api("timeframes(0)") == ["5m", "1h"]
    assert js.api("timeframes(1)") == ["5m", "1h"]


def test_row_a_carries_the_aggregate_columns_and_row_b_does_not(
    js: JsRuntime,
) -> None:
    js.push(bridge_payload(set_summary={"summary": LIVE_SUMMARY, "symbol": "BTC-USD"}))
    assert js.api("titlesOf(0)")[-3:] == surface.AGGREGATE_TITLES
    assert js.api("titlesOf(1)")[-3:] != surface.AGGREGATE_TITLES


def test_the_cell_texts_are_the_ones_the_surface_settled(js: JsRuntime) -> None:
    payload = bridge_payload(
        set_summary={"summary": LIVE_SUMMARY, "symbol": "BTC-USD"}
    )
    js.push(payload)
    printed = js.api("cellTexts(0)")
    settled_text = [
        [cell["text"] for cell in row["cells"]]
        for row in payload["tables"][0]["rows"]
    ]
    assert printed == settled_text, "the module prints the surface's text unchanged"


def test_an_empty_panel_draws_no_rows(js: JsRuntime) -> None:
    js.push(bridge_payload())
    assert js.api("timeframes(0)") == []


# -- 4. the animation, read as a value ---------------------------------


def test_the_frame_interval_is_read_rather_than_timed(js: JsRuntime) -> None:
    js.push(bridge_payload(set_summary={"summary": LIVE_SUMMARY, "symbol": "BTC-USD"}))
    assert js.api("frameInterval(0)") == surface.BARS_FRAME_INTERVAL_MS


def test_one_frame_moves_a_bar_the_published_fraction_of_its_gap(
    js: JsRuntime,
) -> None:
    payload = bridge_payload(
        set_summary={"summary": LIVE_SUMMARY, "symbol": "BTC-USD"}
    )
    js.push(payload)
    before = js.api("barConfidences(0)")
    assert before[0] == 0, "positive control: a bar starts at zero"
    js.run("window.acervatorIndicatorPanel.advance(0, 1);")
    after = js.api("barConfidences(0)")
    target = payload["bars"][0]["targets"][0]["confidence"]
    assert after[0] == pytest.approx(target * surface.BARS_LERP_FACTOR), (
        f"one frame must travel {surface.BARS_LERP_FACTOR} of the gap; "
        f"got {after[0]} toward {target}"
    )


def test_the_animation_settles_on_its_target_after_enough_frames(
    js: JsRuntime,
) -> None:
    payload = bridge_payload(
        set_summary={"summary": LIVE_SUMMARY, "symbol": "BTC-USD"}
    )
    js.push(payload)
    settled = js.json("window.acervatorIndicatorPanel.advance(0, 500)")
    assert settled is True, "the animation must reach its target and stop"
    reached = js.api("barConfidences(0)")
    wanted = [one["confidence"] for one in payload["bars"][0]["targets"]]
    assert reached == pytest.approx(wanted)


def test_the_module_matches_the_surface_frame_for_frame(js: JsRuntime) -> None:
    """The two sides run the same animation, so a panel drawn by either agrees."""
    payload = bridge_payload(
        set_summary={"summary": LIVE_SUMMARY, "symbol": "BTC-USD"}
    )
    js.push(payload)
    js.run("window.acervatorIndicatorPanel.advance(0, 3);")
    reached = js.api("barConfidences(0)")

    model = surface.ConfidenceBarsModel()
    model.set_bars(payload["bars"][0]["targets"])
    for _frame in range(3):
        model.step()
    wanted = [one["confidence"] for one in model.current]
    assert reached == pytest.approx(wanted), (
        f"module {reached} and surface {wanted} must agree frame for frame"
    )


# -- 5. the panel drawn in the real page -------------------------------


class Browser:
    """The real renderer page, loaded from disk in a Chromium view."""

    def __init__(self) -> None:
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
        self._view.resize(900, 600)
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
                if self.js("typeof window.acervatorSetIndicatorPanel") == "function":
                    return
                self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the panel module: readyState "
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
        self.js(
            "window.PANEL = " + json.dumps(payload) + ";"
            "window.HOST = document.createElement('div');"
            "document.body.appendChild(window.HOST);"
            "window.acervatorSetIndicatorPanel(window.PANEL);"
            "window.acervatorIndicatorPanel.renderPanel(window.HOST, window.PANEL);"
        )
        self.settle(READY_STEP_MS)

    def painted(self, part: str, name: str) -> Any:
        return self.js(
            "(function () {"
            "  var node = window.HOST.querySelector('[data-part=\"" + part + "\"]');"
            "  if (!node) { return null; }"
            "  return getComputedStyle(node)." + name + ";"
            "})()"
        )

    def textOf(self, part: str) -> Any:
        return self.js(
            "(function () {"
            "  var node = window.HOST.querySelector('[data-part=\"" + part + "\"]');"
            "  return node ? node.textContent : null;"
            "})()"
        )

    def count(self, part: str) -> Any:
        return self.js(
            "window.HOST.querySelectorAll('[data-part=\"" + part + "\"]').length"
        )

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


def test_the_page_draws_the_panel_and_its_two_mini_panels(browser) -> None:
    browser.draw(
        bridge_payload(set_summary={"summary": LIVE_SUMMARY, "symbol": "BTC-USD"})
    )
    assert browser.count("indicator-panel") == 1
    assert browser.count("indicator-mini-panel") == 2, (
        "the panel stacks two mini-panels, one per indicator row"
    )


def test_the_page_draws_one_table_row_per_timeframe(browser) -> None:
    browser.draw(
        bridge_payload(set_summary={"summary": LIVE_SUMMARY, "symbol": "BTC-USD"})
    )
    cells = browser.js(
        "window.HOST.querySelectorAll('[data-part=\"indicator-body-cell\"]').length"
    )
    assert cells > 0, "the drawn table must carry cells"


def test_the_page_paints_the_staleness_banner_at_the_converted_alpha(
    browser,
) -> None:
    payload = bridge_payload()
    payload["staleness"]["visible"] = True
    payload["staleness"]["text"] = "LAST TA READ, NOT CURRENT"
    browser.draw(payload)
    painted = browser.painted("indicator-staleness", "backgroundColor")
    byte = payload["staleness"]["background_alpha"]
    assert painted is not None, "the banner must be in the page when it is visible"
    assert not painted.startswith("rgb("), (
        "Chromium reports a fully opaque colour as rgb(...), which is what an "
        f"unconverted alpha byte produces; got {painted}"
    )
    assert channels_of(painted) == payload["staleness"]["background_rgb"], (
        f"the page painted {painted}"
    )
    painted_byte = alpha_fraction(painted) * ALPHA_SCALE
    assert painted_byte == pytest.approx(byte, abs=1.0), (
        f"Chromium painted alpha byte {painted_byte} where Qt paints {byte}; "
        f"computed style was {painted}"
    )


def test_the_page_hides_the_staleness_banner_on_a_live_reading(browser) -> None:
    browser.draw(
        bridge_payload(set_summary={"summary": LIVE_SUMMARY, "symbol": "BTC-USD"})
    )
    hidden = browser.js(
        "(function () {"
        "  var n = window.HOST.querySelector('[data-part=\"indicator-staleness\"]');"
        "  return n ? n.hidden : null;"
        "})()"
    )
    assert hidden is True, "a live reading carries no stale banner"


def test_the_page_prints_the_vote_tally_beside_the_title(browser) -> None:
    payload = bridge_payload(
        set_summary={"summary": LIVE_SUMMARY, "symbol": "BTC-USD"}
    )
    browser.draw(payload)
    assert browser.textOf("indicator-summary") == payload["summary_text"]


def test_the_page_prints_the_active_lock_it_was_handed(browser) -> None:
    payload = bridge_payload(
        set_summary={"summary": LIVE_SUMMARY, "symbol": "BTC-USD"}
    )
    browser.draw(payload)
    assert "4h" in browser.textOf("indicator-locks")


def test_the_page_prints_the_rate_strip_it_was_handed(browser) -> None:
    payload = bridge_payload()
    browser.draw(payload)
    assert browser.textOf("indicator-rate-strip") == payload["rate_strip"]["text"]


def test_the_page_says_it_is_waiting_when_there_are_no_bars(browser) -> None:
    browser.draw(bridge_payload())
    assert browser.count("indicator-bars-empty") > 0, (
        "an empty bar pane says what it is waiting for"
    )


def test_the_page_makes_no_network_call(browser) -> None:
    browser.draw(
        bridge_payload(set_summary={"summary": LIVE_SUMMARY, "symbol": "BTC-USD"})
    )
    violations = browser.parsed("window.VIOLATIONS || []")
    assert violations == [], (
        f"the panel must not reach the network under the page policy: {violations}"
    )
