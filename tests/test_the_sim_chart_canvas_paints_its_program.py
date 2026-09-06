"""The React Simulator chart paints the draw program its surface built.

``feed`` drives the inherited ``append_tick`` and ``PAINTED_PIXELS_JS`` counts
what the canvas painted. A chart tracking no symbol is the control.
"""

from __future__ import annotations

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
SETTLE_MS = 400
VIEW_SIZE_PX = (900, 400)
TICKS = 60


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


@pytest.fixture()
def chart(monkeypatch):
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    monkeypatch.setenv("ACERVATOR_VARIANT", "react")
    from src.gui import variant_surface

    made = variant_surface.surface_class(variant_surface.SIM_PRICE_CHART)()
    made.resize(*VIEW_SIZE_PX)
    made.show()
    for _ in range(READY_ROUNDS):
        if made.page_ready:
            break
        settle(READY_STEP_MS)
    yield made
    made.hide()
    made.deleteLater()


def feed(made, symbols) -> None:
    """Track ``symbols`` and append ``TICKS`` bars to each one."""
    made.set_symbols(symbols)
    for step in range(TICKS):
        for at, symbol in enumerate(symbols):
            made.append_tick(
                symbol,
                close_price=100.0 + at * 10 + step * 0.5,
                volume=1.0 + step,
                ts=1_700_000_000_000 + step * 60_000,
                open_price=100.0 + at * 10 + step * 0.4,
                high=100.0 + at * 10 + step * 0.7,
                low=100.0 + at * 10 + step * 0.3,
            )
    made.update()


def painted(made) -> int:
    from src.gui.react_sim_visuals import PAINTED_PIXELS_JS

    return int(js(made._web, PAINTED_PIXELS_JS))


def test_a_chart_tracking_no_symbol_paints_nothing(chart):
    chart.set_symbols([])
    settle(SETTLE_MS)
    assert painted(chart) == 0, "the canvas painted with no symbol to draw"


def test_a_fed_chart_paints_its_bands(chart):
    feed(chart, ["BTC-USD", "ETH-USD", "SOL-USD"])
    settle(SETTLE_MS)
    assert painted(chart) > 0, "the canvas painted none of the draw program"


def test_the_page_is_given_every_step_the_surface_built(chart):
    from src.gui.react_sim_visuals import OPS_COUNT_JS

    feed(chart, ["BTC-USD", "ETH-USD"])
    settle(SETTLE_MS)
    built = len(chart.model()["chart"]["program"])
    assert built > 0, "the surface built no draw program to compare against"
    assert js(chart._web, OPS_COUNT_JS) == str(built)
