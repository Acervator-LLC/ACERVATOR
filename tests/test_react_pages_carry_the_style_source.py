"""Each React page in ``PAGES`` loads the modules ``acervatorHeader`` lives in.

``draw_and_read_title_colour`` reads the colour a page paints with that source
and without it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 200
READY_STEP_MS = 100


def settle(milliseconds: int) -> None:
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def js(view, script: str) -> Any:
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    box: dict = {}

    def _answered(value: Any) -> None:
        box.setdefault("v", value)
        loop.quit()

    view.page().runJavaScript(script, _answered)
    QTimer.singleShot(JS_TIMEOUT_MS, loop.quit)
    loop.exec()
    assert "v" in box, "the browser never answered: " + script[:80]
    return box["v"]


def parsed(view, expression: str) -> Any:
    return json.loads(js(view, "JSON.stringify(" + expression + ")"))


def load(html: str):
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    view = QWebEngineView()
    view.resize(1200, 900)
    box: dict = {}
    view.loadFinished.connect(lambda ok: box.setdefault("ok", ok))
    view.setHtml(html)
    for _ in range(READY_ROUNDS):
        if "ok" in box:
            break
        settle(READY_STEP_MS)
    assert box.get("ok") is True, box
    return view


PAGES = [
    ("sim_stat_strip", "src.gui.react_sim_stat_strip", "strip_html"),
    ("market_inspector", "src.gui.react_market_inspector_tab", "tab_html"),
    ("nuclear_mode_panel", "src.gui.react_nuclear_mode_panel", "panel_html"),
]


@pytest.mark.parametrize("name,module,maker", PAGES)
def test_the_page_carries_the_style_source(name, module, maker):
    import importlib

    page = getattr(importlib.import_module(module), maker)()
    view = load(page)
    print(
        name,
        "acervatorHeader=",
        js(view, "typeof window.acervatorHeader"),
        "acervatorWidgets=",
        js(view, "typeof window.acervatorWidgets"),
        "acervatorTokens=",
        js(view, "typeof window.acervatorTokens"),
        "acervatorThemes=",
        js(view, "typeof window.acervatorThemes"),
    )
    found = js(view, "window.acervatorHeader && typeof window.acervatorHeader.styleOf")
    print(name, "styleOf=", found)
    view.deleteLater()
    assert found == "function", f"{name} loaded no style source: styleOf is {found!r}"


def draw_and_read_title_colour(html: str) -> str:
    """Draw the Nuclear page from ``html`` and read the title's painted colour."""
    import src.gui.react_nuclear_mode_panel as panel_module
    from src.gui.main_tabs import nuclear_mode_panel_surface as surface

    view = load(html)
    for _ in range(READY_ROUNDS):
        if js(view, "typeof window.acervatorNuclearDraw") == "function":
            break
        settle(READY_STEP_MS)
    model = surface.envelope(surface.PanelModel(surface.PanelWorld()).build())
    js(view, panel_module.draw_script(model))
    settle(200)
    found = js(
        view,
        "(function(){var n=document.querySelector('[data-part=\"title\"]');"
        "return n===null?'no-title':getComputedStyle(n).color;})()",
    )
    view.deleteLater()
    return str(found)


def test_the_style_source_is_what_paints_the_nuclear_title_gold():
    import src.gui.react_nuclear_mode_panel as panel_module
    from src.gui.react_history_panel import page_html

    with_source = draw_and_read_title_colour(panel_module.panel_html())
    blind = page_html(
        panel_module.PANEL_STYLE_ASSETS,
        (
            "vendor/react.production.min.js",
            "vendor/react-dom.production.min.js",
            "nuclear_mode_panel.js",
        ),
        panel_module.PANEL_BODY,
        "cyberpunk_dark",
        (panel_module.HOST_SCRIPT,),
    )
    without_source = draw_and_read_title_colour(blind)
    print("TITLE COLOUR with style source:", with_source)
    print("TITLE COLOUR without style source:", without_source)
    assert with_source == "rgb(255, 204, 68)", with_source
    assert without_source != with_source, without_source
