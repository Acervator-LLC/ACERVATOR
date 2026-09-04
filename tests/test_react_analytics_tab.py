"""analytics_tab.js drawn and read back against analytics_tab_surface.

WHAT IS PROVED
==============
The renderer module carries every value the analytics surface publishes,
reports a payload that has drifted, and draws the eight metric cards, the
two tables and the painted equity curve in the real Chromium view the
desktop shell embeds.

The wash under the equity curve is the value that has to survive the
crossing. Qt counts an alpha to 255 and CSS counts it to 1, so the byte
the Qt painter reads would paint a solid block in a browser. The surface
converts on the way out; here the two forms are painted onto a canvas over
the same ground and the pixels are read back, so a conversion that stopped
happening makes the two readings equal and the comparison reports.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.color_alpha import ALPHA_HIGHEST
from src.gui.main_tabs import analytics_tab_surface as surface

MODULE_PATH = REPO_ROOT / "src" / "gui" / "web" / "analytics_tab.js"
MANIFEST_PATH = REPO_ROOT / "desktop" / "renderer" / "module_manifest.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: Read at collection, before any test body reads the file again.
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 100
READY_STEP_MS = 100
PAGE_ATTEMPTS = 2
HOST_WIDTH_PX = 1000
HOST_HEIGHT_PX = 700

CARD_TOTAL = 8
BOT_COLUMN_TOTAL = 10
TIMEFRAME_COLUMN_TOTAL = 4
GROUP_TOTAL = 3

CHART_SIZE = (800, 300)

#: The ground the chart paints on, as the surface writes it.
CHART_GROUND = "#0a0a12"
CHART_GROUND_RGB = (10, 10, 18)

#: The rising wash, in the two forms the byte and the share produce.
RISE_CHANNELS = (0, 255, 136)
RISE_TOP_BYTE = 40

SUMMARY = {
    "total_pnl": 1234.56789,
    "win_rate": 61.25,
    "sharpe_ratio": 1.42,
    "profit_factor": 2.13,
    "total_trades": 128,
    "max_drawdown": 4.75,
    "expectancy": 9.6432,
    "trades_today": 6,
}

RISING_CURVE = [
    {"timestamp": 1000 + step * 60, "equity": 100.0 + step * 1.5} for step in range(6)
]
FALLING_CURVE = [
    {"timestamp": 1000 + step * 60, "equity": 140.0 - step * 2.0} for step in range(6)
]

TIMEFRAMES = {
    "15m": {"total_trades": 40, "win_rate": 55.0, "total_pnl": 12.5},
    "1h": {"total_trades": 22, "win_rate": 63.5, "total_pnl": -3.25},
}


class Perf:
    """One row of the per-bot performance table."""

    def __init__(self, bot_id: str, pnl: float) -> None:
        self.bot_id = bot_id
        self.symbol = "BTC/USD"
        self.total_trades = 11
        self.win_rate = 54.5
        self.total_pnl = pnl
        self.profit_factor = 1.6
        self.sharpe_ratio = 0.9
        self.max_drawdown_pct = 2.5
        self.avg_hold_seconds = 4210.0
        self.expectancy = pnl / 11


BOTS = [Perf("aaaabbbbcccc", 21.5), Perf("ddddeeeeffff", -8.25)]


def published(curve: Any = None, **named: Any) -> dict:
    """The payload the bridge answers with, straight from the handler."""
    request = {
        "summary": SUMMARY,
        "curve": RISING_CURVE if curve is None else curve,
        "bots": [surface.bot_values(one) for one in BOTS],
        "timeframes": TIMEFRAMES,
        "width": CHART_SIZE[0],
        "height": CHART_SIZE[1],
    }
    request.update(named)
    return surface.view_model(request)


def empty_published() -> dict:
    """The payload for a tab that has no numbers yet."""
    return surface.view_model({"width": CHART_SIZE[0], "height": CHART_SIZE[1]})


# -- the module in an engine of its own --------------------------------


class JsRuntime:
    """A QJSEngine holding analytics_tab.js and a ``window`` global."""

    def __init__(self, engine: Any, source: str) -> None:
        self._engine = engine
        engine.evaluate("var window = this;")
        loaded = engine.evaluate(source, MODULE_PATH.name)
        assert not loaded.isError(), MODULE_PATH.name + ": " + loaded.toString()

    def run(self, script: str) -> Any:
        result = self._engine.evaluate(script)
        assert not result.isError(), script[:120] + " -> " + result.toString()
        return result

    def json(self, expression: str) -> Any:
        text = self.run("JSON.stringify(" + expression + ")").toString()
        return None if text == "undefined" else json.loads(text)

    def push(self, payload: Any) -> dict:
        self._engine.globalObject().setProperty("PAYLOAD", json.dumps(payload))
        return self.json("acervatorSetAnalytics(JSON.parse(PAYLOAD))")


@pytest.fixture()
def js(qapp) -> JsRuntime:
    """The module, loaded in a fresh engine."""
    qtqml = pytest.importorskip("PySide6.QtQml")
    assert qapp is not None
    return JsRuntime(qtqml.QJSEngine(), MODULE_SOURCE)


@pytest.fixture()
def loaded(js: JsRuntime) -> JsRuntime:
    """The module holding the surface's filled tab."""
    js.push(published())
    return js


#: Every field the surface publishes, and the module call that answers for it.
MODULE_READERS = {
    "accessible_name": "acervatorAnalytics.accessibleName()",
    "actions": "acervatorAnalytics.actions()",
    "bot_columns": "acervatorAnalytics.botColumns()",
    "bot_fields": "acervatorAnalytics.botFields()",
    "bot_rows": "acervatorAnalytics.botRows()",
    "bot_table": "acervatorAnalytics.botTable()",
    "bottom_splitter": "acervatorAnalytics.bottomSplitter()",
    "card_labels": "acervatorAnalytics.cardLabels()",
    "card_order": "acervatorAnalytics.cardOrder()",
    "card_skin": "acervatorAnalytics.cardSkin()",
    "cards": "acervatorAnalytics.cards()",
    "chart": "acervatorAnalytics.chart()",
    "chart_skin": "acervatorAnalytics.chartSkin()",
    "colors": "acervatorAnalytics.colors()",
    "equity_curve_hours": "acervatorAnalytics.equityCurveHours()",
    "group_order": "acervatorAnalytics.groupOrder()",
    "groups": "acervatorAnalytics.groups()",
    "main_splitter": "acervatorAnalytics.mainSplitter()",
    "number_formats": "acervatorAnalytics.numberFormats()",
    "page": "acervatorAnalytics.page()",
    "skin": "acervatorAnalytics.skin()",
    "summary_defaults": "acervatorAnalytics.summaryDefaults()",
    "timeframe_columns": "acervatorAnalytics.timeframeColumns()",
    "timeframe_fields": "acervatorAnalytics.timeframeFields()",
    "timeframe_rows": "acervatorAnalytics.timeframeRows()",
    "timeframe_table": "acervatorAnalytics.timeframeTable()",
    "timer_delays_ms": "acervatorAnalytics.timerDelaysMs()",
    "timers": "acervatorAnalytics.timers()",
}


def test_every_field_the_surface_publishes_reaches_the_module(js: JsRuntime):
    """A published field has no reader, so the renderer cannot see it."""
    payload = published()
    js.push(payload)
    missing = sorted(set(payload) - set(MODULE_READERS))
    assert not missing, f"{len(missing)} published fields have no reader: {missing}"
    invented = sorted(set(MODULE_READERS) - set(payload))
    assert not invented, f"the module reads fields the surface has none of: {invented}"
    differing = {
        name: (payload[name], js.json(call))
        for name, call in MODULE_READERS.items()
        if js.json(call) != payload[name]
    }
    assert not differing, differing


def test_the_reader_check_reports_a_field_the_module_answers_wrongly(js: JsRuntime):
    """The reader comparison passes whatever the module answers."""
    payload = published()
    payload["accessible_name"] = "Moved"
    js.push(payload)
    assert js.json("acervatorAnalytics.accessibleName()") == "Moved"
    js.push(published())
    assert js.json("acervatorAnalytics.accessibleName()") == "Analytics Tab"


def test_the_module_declares_the_fields_the_surface_publishes(js: JsRuntime):
    """The module's declared field list drifted from the payload."""
    payload = published()
    js.push(payload)
    assert sorted(js.json("acervatorAnalytics.declaredFields()")) == sorted(payload)


def test_a_shipped_payload_raises_no_fault(js: JsRuntime):
    """The renderer reported a fault on the payload the bridge answers with."""
    for name, payload in (
        ("rising", published()),
        ("falling", published(curve=FALLING_CURVE)),
        ("empty", empty_published()),
    ):
        report = js.push(payload)
        assert report["faults"] == [], f"{name} raised {report['faults']}"


def test_the_fault_check_reports_a_field_the_payload_lost(js: JsRuntime):
    """A payload missing a field went through unreported."""
    payload = published()
    del payload["chart_skin"]
    report = js.push(payload)
    named = [one["field"] for one in report["faults"] if one["fault"] == "missing"]
    assert "chart_skin" in named, report["faults"]


def test_the_fault_check_reports_a_card_the_labels_do_not_name(js: JsRuntime):
    """A card carrying a label the surface never published went through."""
    payload = published()
    payload["cards"][0]["label"] = "Invented Label"
    report = js.push(payload)
    named = [one["fault"] for one in report["faults"]]
    assert "unnamed" in named, report["faults"]


def test_the_fault_check_reports_a_row_of_the_wrong_width(js: JsRuntime):
    """A bot row short of the declared columns drew a ragged table."""
    payload = published()
    payload["bot_rows"][0] = payload["bot_rows"][0][:4]
    report = js.push(payload)
    short = [one for one in report["faults"] if one["fault"] == "short-list"]
    assert short, report["faults"]
    assert short[0]["detail"] == 4


def test_the_module_answers_nothing_for_a_payload_that_is_not_an_object(
    js: JsRuntime,
):
    """A refused bridge answer left the module holding a half state."""
    report = js.push([1, 2, 3])
    assert report["declared"] is None
    assert report["held"] is None
    assert report["faults"][0]["fault"] == "not-an-object"
    assert js.json("acervatorAnalytics.isLoaded()") is False


def test_the_counts_the_module_reports_match_the_payload(loaded: JsRuntime):
    """The module counted a different number of cards, columns or rows."""
    report = loaded.push(published())
    assert report["declared"]["cards"] == CARD_TOTAL
    assert report["held"]["cards"] == CARD_TOTAL
    assert report["declared"]["bot_columns"] == BOT_COLUMN_TOTAL
    assert report["held"]["bot_columns"] == BOT_COLUMN_TOTAL
    assert report["declared"]["timeframe_columns"] == TIMEFRAME_COLUMN_TOTAL
    assert report["held"]["timeframe_columns"] == TIMEFRAME_COLUMN_TOTAL
    assert report["held"]["rows"] == len(BOTS) + len(TIMEFRAMES)
    assert report["held"]["cells"] == len(BOTS) * BOT_COLUMN_TOTAL + len(
        TIMEFRAMES
    ) * TIMEFRAME_COLUMN_TOTAL


def test_the_module_names_every_card_the_surface_published(loaded: JsRuntime):
    """A metric card lost its label between the surface and the renderer."""
    titles = loaded.json("acervatorAnalytics.cardTitles()")
    assert titles == [one["label"] for one in published()["cards"]]
    assert len(titles) == CARD_TOTAL
    assert loaded.json("acervatorAnalytics.card('pnl')")["value"] == "$+1,234.5679"
    assert loaded.json("acervatorAnalytics.labelFor('sharpe')") == "Sharpe Ratio"
    assert loaded.json("acervatorAnalytics.card('no_such_card')") is None


# -- the alpha the renderer receives -----------------------------------


def alpha_values(payload: dict) -> list:
    """Every alpha the payload's chart colours carry."""
    found = [one[1][3] for one in payload["chart"]["gradient"]["stops"]]
    for name in ("rise_fill", "fall_fill"):
        found.extend(one[3] for one in payload["chart_skin"][name])
    return found


def test_the_bridge_publishes_a_css_alpha_share_not_qt_s_byte():
    """The renderer was handed the byte CSS clamps to full opacity."""
    for alpha in alpha_values(published()):
        assert 0 < alpha <= 1, alpha
    built = surface.build_view_model(SUMMARY, RISING_CURVE, [], TIMEFRAMES)
    bytes_kept = [one[1][3] for one in built["chart"]["gradient"]["stops"]]
    assert bytes_kept == [RISE_TOP_BYTE, 5], bytes_kept
    assert max(bytes_kept) > 1, "the Qt side stopped carrying a byte"
    assert surface.CHART_RISE_FILL[0][3] == RISE_TOP_BYTE
    assert published()["chart"]["gradient"]["stops"][0][1][3] == (
        RISE_TOP_BYTE / ALPHA_HIGHEST
    )


def test_the_module_reports_a_payload_still_carrying_qt_s_byte(js: JsRuntime):
    """A byte alpha reaching the renderer drew a solid block unreported."""
    payload = published()
    payload["chart"]["gradient"]["stops"][0][1][3] = RISE_TOP_BYTE
    report = js.push(payload)
    named = [one for one in report["faults"] if one["fault"] == "byte-alpha"]
    assert named, report["faults"]
    assert named[0]["detail"] == RISE_TOP_BYTE


def test_the_module_writes_the_share_it_was_given_into_the_colour(loaded: JsRuntime):
    """The module scaled the alpha again, or dropped it."""
    colours = loaded.json("acervatorAnalytics.fillColours()")
    stops = published()["chart"]["gradient"]["stops"]
    assert len(colours) == len(stops)
    for colour, stop in zip(colours, stops):
        assert colour == "rgba(0, 255, 136, " + repr(stop[1][3]) + ")", colour
    assert loaded.json("acervatorAnalytics.rgba([1, 2, 3])") is None


# -- the module is reachable from the shipped page ---------------------


def test_the_manifest_names_the_module():
    """The renderer page never loads a module the manifest does not name."""
    text = MANIFEST_PATH.read_text(encoding="utf-8")
    assert '"' + MODULE_PATH.name + '"' in text
    assert MODULE_PATH.name not in INDEX_HTML.read_text(encoding="utf-8")


def test_the_module_asks_the_bridge_for_the_method_the_surface_registers(
    js: JsRuntime,
):
    """The module asks for a method the bridge does not answer."""
    assert js.json("acervatorAnalytics.method") == surface.METHOD
    from src.core import desktop_bridge

    assert surface.METHOD in desktop_bridge.build_registry()


def test_the_module_reports_a_page_with_no_bridge(js: JsRuntime):
    """A page with no bridge left the module waiting forever."""
    js.run("acervatorLoadAnalytics({});")
    assert js.json("acervatorAnalytics.loadError()") == (
        "the preload bridge is not present"
    )


# -- the tab, drawn in the real page -----------------------------------


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
                if self.js("typeof window.acervatorSetAnalytics") == "function":
                    return
                self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the analytics module: readyState "
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

    def settle(self, milliseconds: int) -> None:
        from PySide6.QtCore import QEventLoop, QTimer

        loop = QEventLoop()
        QTimer.singleShot(milliseconds, loop.quit)
        loop.exec()

    def draw(self, payload: dict) -> None:
        """Renders the tab into a host of a known size."""
        self.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
        self.js(HOST_SCRIPT)
        self.js(
            "window.acervatorAnalytics.renderTab("
            "window.HOST, JSON.parse(window.PAYLOAD));"
        )

    def close(self) -> None:
        self._view.deleteLater()


HOST_SCRIPT = (
    "if (!window.HOST) {"
    "  window.HOST = document.createElement('div');"
    "  window.HOST.style.width = " + json.dumps(str(HOST_WIDTH_PX) + "px") + ";"
    "  window.HOST.style.height = " + json.dumps(str(HOST_HEIGHT_PX) + "px") + ";"
    "  document.body.appendChild(window.HOST);"
    "}"
)

#: Paints one CSS colour over one ground on a canvas and reads the pixel back.
PAINT_SCRIPT = (
    "window.paintOver = function (ground, colour) {"
    "  var canvas = document.createElement('canvas');"
    "  canvas.width = 8; canvas.height = 8;"
    "  var ctx = canvas.getContext('2d');"
    "  ctx.fillStyle = ground; ctx.fillRect(0, 0, 8, 8);"
    "  ctx.fillStyle = colour; ctx.fillRect(0, 0, 8, 8);"
    "  var data = ctx.getImageData(4, 4, 1, 1).data;"
    "  return [data[0], data[1], data[2], data[3]]; };"
)

#: Every drawn part's tag, attributes and computed colours.
READ_PARTS = (
    "(function () {"
    "  var found = [];"
    "  var walk = function (el) {"
    "    var part = el.getAttribute('data-part');"
    "    if (part !== null) {"
    "      var computed = getComputedStyle(el);"
    "      var attrs = {};"
    "      Array.prototype.slice.call(el.attributes).forEach(function (a) {"
    "        attrs[a.name] = a.value; });"
    "      found.push({ part: part, tag: el.tagName.toLowerCase(),"
    "        text: el.textContent, attrs: attrs,"
    "        color: computed.color, fill: computed.fill,"
    "        stroke: computed.stroke,"
    "        background: computed.backgroundColor,"
    "        fontSize: computed.fontSize,"
    "        fontWeight: computed.fontWeight });"
    "    }"
    "    Array.prototype.slice.call(el.children).forEach(walk);"
    "  };"
    "  walk(window.HOST);"
    "  return found; })()"
)


@pytest.fixture()
def browser(qapp):
    """The page, or a skip when Chromium is not installed with Qt."""
    assert qapp is not None
    pytest.importorskip("PySide6.QtWebEngineWidgets")
    page = Browser()
    yield page
    page.close()


def parts_by_name(drawn: list) -> dict:
    """The drawn parts grouped by their data-part name."""
    found: dict = {}
    for one in drawn:
        found.setdefault(one["part"], []).append(one)
    return found


def test_the_page_draws_every_part_the_tab_is_made_of(browser: Browser):
    """A part of the analytics tab reached no element in the page."""
    browser.draw(published())
    drawn = parts_by_name(browser.parsed(READ_PARTS))
    assert len(drawn.get("tab", [])) == 1
    assert len(drawn.get("metrics-row", [])) == 1
    assert len(drawn.get("card", [])) == CARD_TOTAL
    assert len(drawn.get("card-label", [])) == CARD_TOTAL
    assert len(drawn.get("card-value", [])) == CARD_TOTAL
    assert len(drawn.get("split", [])) == 2
    assert len(drawn.get("group", [])) == GROUP_TOTAL
    assert len(drawn.get("table", [])) == 2
    assert len(drawn.get("chart", [])) == 1
    assert len(drawn.get("head-cell", [])) == (
        BOT_COLUMN_TOTAL + TIMEFRAME_COLUMN_TOTAL
    )
    assert len(drawn.get("row", [])) == len(BOTS) + len(TIMEFRAMES)
    assert len(drawn.get("cell", [])) == len(BOTS) * BOT_COLUMN_TOTAL + len(
        TIMEFRAMES
    ) * TIMEFRAME_COLUMN_TOTAL


def test_the_page_draws_the_card_values_the_surface_published(browser: Browser):
    """A metric card shows a number the surface never published."""
    payload = published()
    browser.draw(payload)
    drawn = parts_by_name(browser.parsed(READ_PARTS))
    labels = [one["text"] for one in drawn["card-label"]]
    values = [one["text"] for one in drawn["card-value"]]
    assert labels == [one["label"] for one in payload["cards"]]
    assert values == [one["value"] for one in payload["cards"]]
    assert values[0] == "$+1,234.5679"


def test_the_page_paints_a_gain_green_and_a_loss_red(browser: Browser):
    """A profit card or a loss cell painted the wrong side's colour."""
    browser.draw(published())
    drawn = parts_by_name(browser.parsed(READ_PARTS))
    assert drawn["card-value"][0]["color"] == "rgb(0, 255, 136)"
    losses = [
        one["color"]
        for one in drawn["cell"]
        if one["attrs"].get("data-column") == "4"
        and one["attrs"].get("data-row") == "1"
    ]
    assert losses == ["rgb(255, 51, 102)"], losses
    gains = [
        one["color"]
        for one in drawn["cell"]
        if one["attrs"].get("data-column") == "4"
        and one["attrs"].get("data-row") == "0"
    ]
    assert gains == ["rgb(0, 255, 136)"], gains


def test_the_page_paints_the_rising_curve_green_and_the_falling_curve_red(
    browser: Browser,
):
    """The equity curve painted a loss green, or a gain red."""
    browser.draw(published())
    rising = parts_by_name(browser.parsed(READ_PARTS))["chart-line"]
    assert rising, "the rising curve drew no line"
    assert {one["stroke"] for one in rising} == {"rgb(0, 255, 136)"}
    browser.draw(published(curve=FALLING_CURVE))
    falling = parts_by_name(browser.parsed(READ_PARTS))["chart-line"]
    assert {one["stroke"] for one in falling} == {"rgb(255, 51, 102)"}


def test_the_page_shows_the_waiting_chart_when_there_is_no_curve(browser: Browser):
    """A tab with no equity points drew a curve out of nothing."""
    browser.draw(empty_published())
    drawn = parts_by_name(browser.parsed(READ_PARTS))
    assert drawn["chart"][0]["attrs"]["data-empty"] == "true"
    assert drawn["chart-empty"][0]["text"] == "Collecting equity data..."
    assert "chart-line" not in drawn
    assert "chart-fill" not in drawn


def test_the_page_makes_no_content_policy_complaint(browser: Browser):
    """Drawing the tab tripped the page's content policy."""
    browser.js(
        "window.VIOLATIONS = [];"
        "document.addEventListener('securitypolicyviolation', function (e) {"
        "  window.VIOLATIONS.push(e.violatedDirective + ' ' + e.blockedURI); });"
    )
    browser.draw(published())
    browser.settle(READY_STEP_MS)
    assert browser.parsed("window.VIOLATIONS") == []


# -- the wash under the curve, read off a painted pixel ----------------


def blend(ground: tuple, channels: tuple, share: float) -> tuple:
    """The colour a browser composites for one share over one ground."""
    return tuple(
        round(ground[at] * (1 - share) + channels[at] * share) for at in range(3)
    )


def test_the_published_wash_paints_at_its_own_transparency(browser: Browser):
    """The wash under the equity curve painted as a solid block.

    The share the surface publishes and the byte Qt reads are painted
    over the same ground. The byte must come back opaque, which is the
    control: a conversion that stopped happening makes both readings the
    opaque one and this comparison reports.
    """
    browser.js(PAINT_SCRIPT)
    payload = published()
    share = payload["chart"]["gradient"]["stops"][0][1][3]
    published_colour = "rgba(0, 255, 136, " + repr(share) + ")"
    qt_colour = "rgba(0, 255, 136, " + str(RISE_TOP_BYTE) + ")"
    painted = browser.parsed(
        "window.paintOver("
        + json.dumps(CHART_GROUND)
        + ", "
        + json.dumps(published_colour)
        + ")"
    )
    clamped = browser.parsed(
        "window.paintOver("
        + json.dumps(CHART_GROUND)
        + ", "
        + json.dumps(qt_colour)
        + ")"
    )
    assert tuple(clamped[:3]) == RISE_CHANNELS, clamped
    assert tuple(painted[:3]) != RISE_CHANNELS, painted
    wanted = blend(CHART_GROUND_RGB, RISE_CHANNELS, share)
    assert all(abs(painted[at] - wanted[at]) <= 1 for at in range(3)), (
        painted,
        wanted,
    )


def test_the_drawn_chart_fill_carries_the_published_share(browser: Browser):
    """The gradient the chart fills with lost the share on the way in."""
    payload = published()
    browser.draw(payload)
    stops = browser.parsed(
        "Array.prototype.slice.call("
        "window.HOST.querySelectorAll('stop')).map(function (one) {"
        "  return [one.getAttribute('offset'),"
        "    getComputedStyle(one).stopColor]; })"
    )
    assert len(stops) == len(payload["chart"]["gradient"]["stops"])
    for drawn, stop in zip(stops, payload["chart"]["gradient"]["stops"]):
        assert drawn[0] == str(stop[0])
        assert drawn[1].startswith("rgba(0, 255, 136,"), drawn
        share = float(drawn[1].rstrip(")").split(",")[-1])
        assert abs(share - stop[1][3]) < 0.01, drawn


def test_the_pixel_reader_can_tell_two_colours_apart(browser: Browser):
    """The canvas reader answers the same for any colour it is given."""
    browser.js(PAINT_SCRIPT)
    ground = browser.parsed(
        "window.paintOver(" + json.dumps(CHART_GROUND) + ", 'rgba(0, 0, 0, 0)')"
    )
    solid = browser.parsed(
        "window.paintOver(" + json.dumps(CHART_GROUND) + ", 'rgb(0, 255, 136)')"
    )
    assert tuple(ground[:3]) == CHART_GROUND_RGB, ground
    assert tuple(solid[:3]) == RISE_CHANNELS, solid
    assert ground[:3] != solid[:3]
