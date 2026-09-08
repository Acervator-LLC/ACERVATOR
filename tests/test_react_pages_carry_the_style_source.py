"""Each React page in ``PAGES`` loads the modules ``acervatorHeader`` lives in."""

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
    ("market_inspector", "src.gui.react_market_inspector_tab", "tab_html"),
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
