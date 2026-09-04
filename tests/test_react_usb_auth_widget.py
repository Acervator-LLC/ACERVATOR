"""``usb_auth_widget.js`` against ``usb_auth_widget_surface.py``.

WHAT IS PROVED
==============
The USB hardware key panel is drawn by the renderer from the payload
``usb_auth_widget.state`` publishes, and the Qt widget it replaces is
still whole.

Qt counts the fourth ``rgba`` field to 255 and CSS counts it to 1, and a
browser clamps anything above 1 to full opacity. ``build_view_model``
keeps Qt's byte, because the Qt widget paints from it. ``view_model``,
the bridge handler, publishes through ``src.gui.color_alpha.css_colours``
so the renderer receives the share a browser reads. Both readings are
taken here, and the Qt form is painted as the control: it must come back
opaque, or the comparison below proves nothing.

The colour is read off a composited canvas pixel rather than a style
getter, so what is asserted is what the engine actually painted.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

from src.core import desktop_bridge
from src.gui.color_alpha import ALPHA_HIGHEST, css_alpha
from src.gui.main_tabs import usb_auth_widget_surface as surface

MODULE_PATH = REPO_ROOT / "src" / "gui" / "web" / "usb_auth_widget.js"
MANIFEST_PATH = REPO_ROOT / "desktop" / "renderer" / "module_manifest.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 100
READY_STEP_MS = 100

#: One ``rgba`` call inside a style sheet.
RGBA_CALL = re.compile(r"rgba\([^()]*\)")

#: The white the published colour is composited over on the canvas.
BACKDROP = (255, 255, 255)

#: How far a composited channel may sit from the arithmetic answer.
CHANNEL_TOLERANCE = 2

#: Qt darkens the lamp's pen by this percentage of its HSV value.
DARKER_PCT = surface.LAMP_PEN_DARKER_PCT

EXCHANGE = {
    "exchange_id": "coinbase",
    "display_name": "Coinbase",
    "hardware_mode": True,
    "hw_volume_serial": "SER123456789",
}

SECOND_EXCHANGE = {
    "exchange_id": "kraken",
    "display_name": "Kraken",
    "hardware_mode": False,
    "hw_volume_serial": "",
}

PAGE_HELPERS = (
    "window.paintedPixel = function (colour) {"
    "  var canvas = document.createElement('canvas');"
    "  canvas.width = 8; canvas.height = 8;"
    "  var pen = canvas.getContext('2d');"
    "  pen.fillStyle = 'rgb(255,255,255)';"
    "  pen.fillRect(0, 0, 8, 8);"
    "  pen.fillStyle = colour;"
    "  pen.fillRect(0, 0, 8, 8);"
    "  var data = pen.getImageData(4, 4, 1, 1).data;"
    "  return [data[0], data[1], data[2], data[3]]; };"
    "window.computedBackground = function (declaration) {"
    "  var probe = document.createElement('div');"
    "  probe.style.cssText = declaration;"
    "  document.body.appendChild(probe);"
    "  var found = getComputedStyle(probe).backgroundColor;"
    "  probe.remove();"
    "  return found; };"
)


def published(**params: Any) -> dict:
    """The bridge handler's answer after the round trip through JSON."""
    return json.loads(json.dumps(surface.view_model(params), ensure_ascii=True))


def one_exchange_payload() -> dict:
    return published(reset=True, exchanges=[EXCHANGE])


def fields_of(call: str) -> list:
    """The four fields of one ``rgba`` call, as written."""
    return call[call.index("(") + 1 : call.rindex(")")].split(",")


def alpha_of(call: str) -> float:
    """The fourth field of one ``rgba`` call."""
    return float(fields_of(call)[3])


def rgb_of(call: str) -> list:
    """The three colour fields of one ``rgba`` call, as written."""
    return fields_of(call)[:3]


def background_of(sheet: str) -> str:
    """The one ``background`` a Qt style sheet's first block names."""
    body = sheet.split("{", 1)[1].split("}", 1)[0]
    found = [
        one.split(":", 1)[1].strip()
        for one in body.split(";")
        if one.split(":", 1)[0].strip() == "background"
    ]
    assert len(found) == 1, f"one background expected, read {found}"
    return found[0]


def composited(colour: tuple[int, int, int], share: float) -> tuple[float, ...]:
    """``colour`` laid over the white backdrop at ``share`` of full opacity."""
    return tuple(
        BACKDROP[at] * (1 - share) + colour[at] * share for at in range(len(BACKDROP))
    )


# -- the bridge boundary -----------------------------------------------


def test_the_published_toggle_style_carries_the_share_css_reads():
    """The renderer reads the fourth field to one, so the bridge must
    publish the share and not the byte the Qt widget paints from."""
    row = one_exchange_payload()["rows"][0]
    share = alpha_of(background_of(row["toggle_style"]))
    assert share <= 1, (
        f"the published toggle style carries the alpha {share}, which a browser "
        f"clamps to full opacity: {row['toggle_style']}"
    )


def test_the_built_toggle_style_still_carries_the_alpha_byte_qt_reads():
    """The control for the check above. Qt paints from this table and reads
    the fourth field to 255, so a share here would paint almost nothing."""
    surface.view_model({"reset": True, "exchanges": [EXCHANGE]})
    row = surface.build_view_model(surface.panel_model())["rows"][0]
    byte = alpha_of(background_of(row["toggle_style"]))
    assert 1 < byte <= ALPHA_HIGHEST, (
        f"the Qt widget paints from this style and it carries {byte}: "
        f"{row['toggle_style']}"
    )


def test_the_published_button_style_carries_the_share_css_reads():
    """The export button's hover tint crosses the same boundary."""
    sheet = one_exchange_payload()["export_style"]
    shares = [alpha_of(one) for one in RGBA_CALL.findall(sheet)]
    assert shares and all(one <= 1 for one in shares), (
        f"the published export style carries the alphas {shares}: {sheet}"
    )


def test_the_bridge_registers_the_panel_handler():
    """The renderer reaches the surface by this method and no other."""
    registry = desktop_bridge.build_registry()
    assert registry[surface.METHOD] is surface.view_model


# -- what the engine actually paints -----------------------------------


class Browser:
    """The real renderer page, loaded from disk in a Chromium view."""

    def __init__(self) -> None:
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
        self.open_page()
        self.wait_for_modules()
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

    def wait_for_modules(self) -> None:
        """Turn the event loop until the panel module has run.

        Rounds, not elapsed time: Chromium throttles an offscreen view's
        timers, so how long this takes is not a value to assert on.
        """
        for _ in range(READY_ROUNDS):
            if self.parsed("typeof window.acervatorUsbAuth") == "object":
                return
            self.settle(READY_STEP_MS)
        raise AssertionError("usb_auth_widget.js never reached the page")

    def js(self, script: str) -> Any:
        from PySide6.QtCore import QEventLoop, QTimer

        loop = QEventLoop()
        box: dict = {}

        def _done(value: Any) -> None:
            box["v"] = value
            loop.quit()

        self._view.page().runJavaScript(script, _done)
        QTimer.singleShot(JS_TIMEOUT_MS, loop.quit)
        loop.exec()
        return box.get("v")

    def parsed(self, expression: str) -> Any:
        return json.loads(self.js("JSON.stringify(" + expression + ")"))

    def settle(self, milliseconds: int) -> None:
        from PySide6.QtCore import QEventLoop, QTimer

        loop = QEventLoop()
        QTimer.singleShot(milliseconds, loop.quit)
        loop.exec()

    def pixel(self, colour: str) -> list:
        """The pixel the engine paints for ``colour`` over white."""
        return self.parsed("window.paintedPixel(" + json.dumps(colour) + ")")

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


def test_the_toggle_background_in_qt_s_own_form_paints_fully_opaque(browser: Browser):
    """The control the check below is measured against. A browser clamps a
    fourth field above one, so Qt's byte paints the colour solid."""
    surface.view_model({"reset": True, "exchanges": [EXCHANGE]})
    built = surface.build_view_model(surface.panel_model())["rows"][0]
    written = background_of(built["toggle_style"])
    painted = browser.pixel(written)
    solid = [int(one.strip()) for one in rgb_of(written)]
    assert painted[:3] == solid, (
        f"{written} painted {painted}; the engine no longer clamps an alpha "
        "byte, so the transparency check below proves nothing"
    )


def test_the_published_toggle_background_paints_at_its_own_transparency(
    browser: Browser,
):
    """What the renderer receives must reach the canvas as a tint."""
    row = one_exchange_payload()["rows"][0]
    written = background_of(row["toggle_style"])
    share = alpha_of(written)
    channels = [int(one.strip()) for one in rgb_of(written)]
    painted = browser.pixel(written)
    wanted = composited((channels[0], channels[1], channels[2]), share)
    for at, expected in enumerate(wanted):
        assert abs(painted[at] - expected) <= CHANNEL_TOLERANCE, (
            f"{written} over white painted {painted}, and the share {share} "
            f"composites to {[round(one) for one in wanted]}"
        )


def test_the_two_forms_of_the_toggle_background_paint_differently(browser: Browser):
    """The two readings must not have collapsed into one, which is what a
    conversion that silently stopped happening would look like."""
    surface.view_model({"reset": True, "exchanges": [EXCHANGE]})
    qt_form = background_of(
        surface.build_view_model(surface.panel_model())["rows"][0]["toggle_style"]
    )
    css_form = background_of(one_exchange_payload()["rows"][0]["toggle_style"])
    assert browser.pixel(qt_form) != browser.pixel(css_form), (
        f"Qt's {qt_form} and the published {css_form} painted one pixel, so the "
        "boundary conversion is not happening"
    )


# -- the renderer ------------------------------------------------------


def test_the_renderer_reports_no_fault_for_the_published_payload(browser: Browser):
    """Every field the module declares is present in what the bridge sends."""
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(one_exchange_payload())))
    faults = browser.parsed(
        "(function () { acervatorSetUsbAuth(JSON.parse(window.PAYLOAD));"
        " return acervatorUsbAuth.faults(); })()"
    )
    assert faults == [], f"the renderer refused the published payload: {faults}"


def test_the_renderer_reports_a_field_the_payload_lost(browser: Browser):
    """The control for the check above. A payload missing a declared field
    must be reported, or an empty fault list means nothing."""
    payload = one_exchange_payload()
    del payload["header_text"]
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)))
    faults = browser.parsed(
        "(function () { acervatorSetUsbAuth(JSON.parse(window.PAYLOAD));"
        " return acervatorUsbAuth.faults(); })()"
    )
    assert any(one["field"] == "header_text" for one in faults), (
        f"a payload with no header_text drew no fault: {faults}"
    )


def test_the_renderer_reports_a_style_still_carrying_the_alpha_byte(browser: Browser):
    """The renderer refuses Qt's form, so a boundary that stopped converting
    is reported at the page rather than painted as a solid block."""
    surface.view_model({"reset": True, "exchanges": [EXCHANGE]})
    payload = json.loads(
        json.dumps(surface.build_view_model(surface.panel_model()), ensure_ascii=True)
    )
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)))
    faults = browser.parsed(
        "(function () { acervatorSetUsbAuth(JSON.parse(window.PAYLOAD));"
        " return acervatorUsbAuth.faults(); })()"
    )
    assert any(one["fault"] == "alpha-byte" for one in faults), (
        f"a payload carrying Qt's alpha byte drew no fault: {faults}"
    )


def test_the_renderer_draws_one_row_for_every_exchange(browser: Browser):
    """The panel's row list is what the exchange rows of the payload say."""
    payload = published(reset=True, exchanges=[EXCHANGE, SECOND_EXCHANGE])
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)))
    drawn = browser.parsed(
        "(function () { var host = document.createElement('div');"
        " document.body.appendChild(host);"
        " acervatorSetUsbAuth(JSON.parse(window.PAYLOAD));"
        " acervatorUsbAuth.renderPanel(host);"
        " var found = host.querySelectorAll(\"[data-part='row']\");"
        " var names = []; var at;"
        " for (at = 0; at < found.length; at += 1) {"
        "   names.push(found[at].getAttribute('data-exchange-id')); }"
        " host.remove(); return names; })()"
    )
    assert drawn == ["coinbase", "kraken"], (
        f"two exchanges were published and the panel drew {drawn}"
    )


def test_the_renderer_draws_the_empty_note_when_no_exchange_is_configured(
    browser: Browser,
):
    """The control for the check above: the same panel with no exchange
    draws no row, and says so."""
    payload = published(reset=True, exchanges=[])
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)))
    drawn = browser.parsed(
        "(function () { var host = document.createElement('div');"
        " document.body.appendChild(host);"
        " acervatorSetUsbAuth(JSON.parse(window.PAYLOAD));"
        " acervatorUsbAuth.renderPanel(host);"
        " var rows = host.querySelectorAll(\"[data-part='row']\").length;"
        " var note = host.querySelector(\"[data-part='empty']\");"
        " var text = note === null ? null : note.textContent;"
        " host.remove(); return [rows, text]; })()"
    )
    assert drawn == [0, payload["empty_text"]], (
        f"no exchange was published and the panel drew {drawn}"
    )


def test_the_lamp_pen_darkens_the_way_qt_darkens(browser: Browser):
    """The surface publishes the darkening as a request, so the renderer
    applies Qt's own rule and must land where QColor does."""
    from PySide6.QtGui import QColor

    payload = one_exchange_payload()
    colour = payload["rows"][0]["lamp"]["colour"]
    drawn = browser.parsed(
        "acervatorUsbAuth.darker("
        + json.dumps(colour)
        + ", "
        + json.dumps(DARKER_PCT)
        + ")"
    )
    wanted = QColor(colour).darker(DARKER_PCT)
    painted = QColor(drawn)
    assert painted.isValid(), f"the renderer answered {drawn} for {colour}"
    for name, got, want in (
        ("red", painted.red(), wanted.red()),
        ("green", painted.green(), wanted.green()),
        ("blue", painted.blue(), wanted.blue()),
    ):
        assert abs(got - want) <= CHANNEL_TOLERANCE, (
            f"{colour} darkened by {DARKER_PCT}: the renderer answered {drawn} "
            f"and QColor answers {wanted.name()}, {name} {got} against {want}"
        )


def test_the_renderer_module_is_named_by_the_generated_manifest():
    """The shell loads what the manifest names, so an unnamed module never
    reaches the page."""
    named = MANIFEST_PATH.read_text(encoding="utf-8")
    assert json.dumps(MODULE_PATH.name) in named, (
        f"{MODULE_PATH.name} is not in the generated manifest; run "
        "tools.sync_renderer_modules"
    )


# -- the Qt widget stays whole -----------------------------------------


class _Settings:
    """The settings object the shipped widget reads its exchanges from."""

    def __init__(self, exchanges: list) -> None:
        self._settings = self
        self.exchanges = exchanges
        self.saved = 0

    def save(self) -> None:
        self.saved += 1


def drain_deferred_deletes() -> None:
    """Carry out the deletions Qt has queued but not yet performed.

    ``deleteLater`` only marks a widget, so a rebuilt row list still holds
    the old rows until the event loop runs. This drains that queue
    directly rather than waiting, which no assertion here may depend on.
    """
    from PySide6.QtCore import QCoreApplication, QEvent

    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _live_children(widget) -> dict:
    """How many of each Qt child the panel is holding."""
    from PySide6.QtWidgets import (
        QComboBox,
        QGroupBox,
        QProgressBar,
        QPushButton,
        QScrollArea,
    )

    return {
        one.__name__: len(widget.findChildren(one))
        for one in (QComboBox, QGroupBox, QProgressBar, QPushButton, QScrollArea)
    }


@pytest.fixture()
def shipped_panel(qapp):
    """The real Qt widget, built but never turned, so its opening scan
    never runs and no drive is read."""
    assert qapp is not None
    from src.gui.usb_auth_widget import USBAuthWidget

    panel = USBAuthWidget(_Settings([dict(EXCHANGE)]), None, None)
    yield panel
    panel.deleteLater()


def test_the_shipped_widget_still_holds_every_live_qt_child(shipped_panel):
    """The Qt panel is preserved until the renderer is verified in the
    operational logs. This fails the moment one of its children is
    deleted, which is what a conversion that removed the Qt path would
    do."""
    held = _live_children(shipped_panel)
    assert held == {
        "QComboBox": 1,
        "QGroupBox": 2,
        "QProgressBar": 1,
        "QPushButton": 4,
        "QScrollArea": 1,
    }, f"the shipped panel is holding {held}"


def test_the_child_count_reports_a_panel_that_lost_its_children(qapp):
    """The control for the check above. A bare widget holds none of them,
    so the count is reading the real object tree and not a constant."""
    assert qapp is not None
    from PySide6.QtWidgets import QWidget

    bare = QWidget()
    held = _live_children(bare)
    assert set(held.values()) == {0}, f"a bare widget reported {held}"
    bare.deleteLater()


def test_the_shipped_widget_rebuilds_its_rows_when_the_exchanges_change(
    shipped_panel,
):
    """``refresh_exchanges`` is what the settings screen calls after an
    exchange is added, and it must reach the real Qt row list."""
    from src.gui.usb_auth_widget import _ExchangeHWRow

    assert len(shipped_panel.findChildren(_ExchangeHWRow)) == 1
    shipped_panel._settings.exchanges.append(dict(SECOND_EXCHANGE))
    shipped_panel.refresh_exchanges()
    drain_deferred_deletes()
    assert len(shipped_panel.findChildren(_ExchangeHWRow)) == 2


def test_the_alpha_share_is_the_byte_over_the_highest(browser: Browser):
    """The arithmetic the boundary uses, stated once and checked against
    what the page paints for the published value."""
    row = one_exchange_payload()["rows"][0]
    written = background_of(row["toggle_style"])
    surface.view_model({"reset": True, "exchanges": [EXCHANGE]})
    byte = alpha_of(
        background_of(
            surface.build_view_model(surface.panel_model())["rows"][0]["toggle_style"]
        )
    )
    assert abs(alpha_of(written) - css_alpha(byte)) <= 0.001, (
        f"the byte {byte} published the share {alpha_of(written)}"
    )
