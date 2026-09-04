"""What a browser paints for the transparency a surface publishes.

WHAT IS PROVED
==============
Qt counts the fourth ``rgba`` field to 255 and CSS counts it to 1, and a
browser clamps anything above 1 to full opacity. A surface that hands the
renderer Qt's byte therefore paints an opaque block where the design asks
for a tint.

``src/gui/color_alpha.py`` converts the byte to the share on the Python
side, and ``design_system_surface``, ``theme_engine_surface`` and
``header_strip_surface`` publish through it. Here the same colour is
painted twice in the real Chromium view the desktop shell embeds: once in
Qt's form, which must come back opaque, and once as the surface publishes
it, which must come back at its own transparency.

The opaque reading is the control. It is not a record of an old defect --
it is the reading the engine still gives Qt's form today, so a conversion
that quietly stopped happening would make the two readings equal and the
comparison would report.

The Qt side is checked here too: the tables the widgets paint from must
still carry the byte, because Qt reads the byte and would paint those
values almost invisible if they were shares.
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

from src.gui import design_system as shipped_tokens
from src.gui import theme_engine as shipped_themes
from src.gui.color_alpha import ALPHA_HIGHEST, css_alpha, css_colours, css_rgba
from src.gui.main_tabs import design_system_surface as dss
from src.gui.main_tabs import header_strip_surface as hss
from src.gui.main_tabs import theme_engine_surface as tes

INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 100
READY_STEP_MS = 100
PAGE_ATTEMPTS = 2

#: A theme every table holds, whose glow and border both carry an alpha byte.
THEME_NAME = "cyberpunk_dark"

#: The design tokens whose value is an rgba call carrying Qt's alpha byte.
BYTE_TOKEN_NAMES = (
    "GLOW_PRIMARY",
    "GLOW_SECONDARY",
    "SCRIM",
    "GLOW_PRIMARY_EDGE",
    "GLOW_PRIMARY_FAINT",
)

#: The theme fields whose value is an rgba call carrying Qt's alpha byte.
BYTE_THEME_FIELDS = ("border_accent", "glow_color")

#: Written into the page so a probe can read one declaration back computed.
PAGE_HELPERS = (
    "window.probeStyle = function (cssText, names) {"
    "  var probe = document.createElement('div');"
    "  probe.style.cssText = cssText;"
    "  document.body.appendChild(probe);"
    "  var computed = getComputedStyle(probe);"
    "  var found = {};"
    "  names.forEach(function (n) { found[n] = computed[n]; });"
    "  probe.remove();"
    "  return found; };"
)

#: A computed colour a browser writes with no fourth field is fully opaque.
OPAQUE_MARK = "rgb("
SHARE_MARK = "rgba("


def payload(module: Any, **params: Any) -> dict:
    """One surface's answer after the round trip through the bridge's JSON."""
    return json.loads(json.dumps(module.view_model(params), ensure_ascii=True))


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
        """Opens the page again while a module global stays absent."""
        for attempt in range(PAGE_ATTEMPTS):
            if attempt:
                self.open_page()
            for _ in range(READY_ROUNDS):
                if self.js("typeof window.acervatorSetTokens") == "function":
                    return
                self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the token module: readyState "
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

    def probe(self, declaration: str, name: str) -> str:
        """The value the engine computes for one declaration on a bare element."""
        found = self.parsed(
            "window.probeStyle("
            + json.dumps(declaration)
            + ", "
            + json.dumps([name])
            + ")"
        )
        return found[name]

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


@pytest.fixture()
def with_tokens(browser: Browser) -> Browser:
    """The page with the real design tokens written into its stylesheet."""
    browser.js("window.TOKENS = " + json.dumps(json.dumps(payload(dss))) + ";")
    written = browser.parsed(
        "(function () { acervatorSetTokens(JSON.parse(window.TOKENS));"
        " return acervatorTokens.apply(document.documentElement); })()"
    )
    assert written, "no design token reached the page's stylesheet"
    return browser


@pytest.fixture()
def with_theme(browser: Browser) -> Browser:
    """The page with the real theme table written into its stylesheet."""
    browser.js(
        "window.THEMES = " + json.dumps(json.dumps(payload(tes, name=THEME_NAME))) + ";"
    )
    written = browser.parsed(
        "(function () { acervatorSetThemes(JSON.parse(window.THEMES));"
        " acervatorThemes.select(" + json.dumps(THEME_NAME) + ");"
        " return acervatorThemes.apply(document.documentElement); })()"
    )
    assert written, "no theme value reached the page's stylesheet"
    return browser


# -- 1. the control: Qt's form still paints opaque ---------------------


@pytest.mark.parametrize("name", BYTE_TOKEN_NAMES)
def test_a_design_token_in_qt_s_own_form_paints_fully_opaque(
    browser: Browser, name: str
):
    """The control the two checks below are measured against. A browser
    clamps a fourth field above one, so Qt's byte paints a solid block."""
    written = getattr(shipped_tokens, name)
    painted = browser.probe("background: " + written, "backgroundColor")
    assert painted.startswith(OPAQUE_MARK) and not painted.startswith(SHARE_MARK), (
        f"{name} was written {written} and painted {painted}; the engine no longer "
        "clamps an alpha byte, so the checks below prove nothing"
    )


# -- 2. what the surfaces publish paints at its own transparency -------


@pytest.mark.parametrize("name", BYTE_TOKEN_NAMES)
def test_a_published_design_token_paints_at_its_own_transparency(
    with_tokens: Browser, name: str
):
    """The token reaches the page as a CSS custom property, so what it paints
    is what every screen drawing from that variable paints."""
    painted = with_tokens.probe("background: var(--" + name + ")", "backgroundColor")
    byte = float(getattr(shipped_tokens, name)[len("rgba(") : -1].split(",")[3])
    assert painted.startswith(
        SHARE_MARK
    ), f"{name} painted {painted}, with no transparency at all"
    share = float(painted[len("rgba(") : -1].split(",")[3])
    assert (
        abs(share - css_alpha(byte)) <= 0.001
    ), f"{name} carries the byte {byte} and painted the share {share}"


@pytest.mark.parametrize("field", BYTE_THEME_FIELDS)
def test_a_published_theme_value_paints_at_its_own_transparency(
    with_theme: Browser, field: str
):
    """The theme writes each field as a CSS custom property under its own name."""
    painted = with_theme.probe("background: var(--" + field + ")", "backgroundColor")
    written = getattr(shipped_themes.THEMES[THEME_NAME], field)
    byte = float(written[len("rgba(") : -1].split(",")[3])
    assert painted.startswith(
        SHARE_MARK
    ), f"{field} painted {painted}, with no transparency at all"
    share = float(painted[len("rgba(") : -1].split(",")[3])
    assert (
        abs(share - css_alpha(byte)) <= 0.001
    ), f"{field} carries the byte {byte} and painted the share {share}"


def test_the_published_header_button_paints_at_its_own_transparency(
    browser: Browser,
):
    """The strip publishes a Qt style sheet and the renderer reads its
    declarations, so the background it names must arrive as a share."""
    published = payload(hss)["mode_button"]["style_sheet"]
    body = published.split("{")[1].split("}")[0]
    background = [
        one.split(":", 1)[1].strip()
        for one in body.split(";")
        if one.split(":", 1)[0].strip() == "background"
    ]
    assert len(background) == 1, f"one background expected, read {background}"
    painted = browser.probe("background: " + background[0], "backgroundColor")
    assert painted.startswith(
        SHARE_MARK
    ), f"the mode button published {background[0]} and painted {painted}"


# -- 3. Qt still reads the byte ----------------------------------------


@pytest.mark.parametrize("name", BYTE_TOKEN_NAMES)
def test_the_shipped_token_table_still_carries_the_alpha_byte(name: str):
    """Qt paints from this table and reads the fourth field to 255, so a share
    here would paint almost nothing."""
    byte = float(getattr(shipped_tokens, name)[len("rgba(") : -1].split(",")[3])
    assert byte > 1, name
    assert byte <= ALPHA_HIGHEST, name


@pytest.mark.parametrize("field", BYTE_THEME_FIELDS)
def test_the_shipped_theme_table_still_carries_the_alpha_byte(field: str):
    """The same, for the table the window's style sheet is built from."""
    written = getattr(shipped_themes.THEMES[THEME_NAME], field)
    byte = float(written[len("rgba(") : -1].split(",")[3])
    assert byte > 1, field
    assert byte <= ALPHA_HIGHEST, field


# -- 4. the converter itself -------------------------------------------


def test_the_converter_turns_qt_s_byte_into_the_share_css_reads():
    """The one conversion every surface publishes through."""
    assert css_rgba("rgba(0,255,204,51)") == "rgba(0,255,204,0.2)"
    assert css_rgba("border: 1px solid rgba(0,255,204,68)") == (
        "border: 1px solid rgba(0,255,204,0.26666666666666666)"
    )


def test_the_converter_leaves_a_share_and_a_colour_it_cannot_read_alone():
    """Converting twice would fade a colour further on every round trip."""
    assert css_rgba("rgba(1,2,3,0.25)") == "rgba(1,2,3,0.25)"
    assert css_rgba("rgba(1,2,3,1)") == "rgba(1,2,3,1)"
    assert css_rgba("rgba(1,2,3,0)") == "rgba(1,2,3,0)"
    assert css_rgba("#0a0a0f") == "#0a0a0f"
    assert css_rgba("rgb(1,2,3)") == "rgb(1,2,3)"


def test_the_converter_reaches_every_colour_of_a_qt_only_value():
    """A Qt gradient keeps its own shape and every colour inside it converts."""
    written = (
        "qlineargradient(x1:0, y1:0, x2:1, y2:0, "
        "stop:0 rgba(0,40,30,200), stop:1 rgba(0,60,45,200))"
    )
    converted = css_rgba(written)
    assert converted.startswith("qlineargradient(x1:0, y1:0, x2:1, y2:0,")
    assert converted.count("rgba(") == 2
    assert "200)" not in converted


def test_the_converter_carries_a_view_model_through_unflattened():
    """A payload keeps its shape, its numbers and its names; only the alpha
    byte of an rgba call moves."""
    carried = css_colours(
        {
            "colour": "rgba(0,255,204,51)",
            "size": 16,
            "on": True,
            "names": ["a", "rgba(0,0,0,136)"],
            "nested": {"edge": "rgba(0,255,204,85)"},
            "pair": ("rgba(0,255,204,34)",),
            "nothing": None,
        }
    )
    assert carried["colour"] == "rgba(0,255,204,0.2)"
    assert carried["size"] == 16
    assert carried["on"] is True
    assert carried["names"] == ["a", "rgba(0,0,0,0.5333333333333333)"]
    assert carried["nested"]["edge"] == "rgba(0,255,204,0.3333333333333333)"
    assert isinstance(carried["pair"], tuple)
    assert carried["nothing"] is None
