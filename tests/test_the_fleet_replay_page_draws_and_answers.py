"""The React Fleet Replay panel draws its chrome and answers a press.

``STATUS_TEXT_JS`` and ``ROW_COUNT_JS`` read what the page drew; a press on the
page runs the inherited ``_on_reset_clicked``.
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
SETTLE_MS = 400
CONFIGS = [
    {"symbol": "BTC-USD", "target_balance": 100.0},
    {"symbol": "ETH-USD", "target_balance": 250.0},
]
RESET_CLICK_JS = (
    "Array.from(document.querySelectorAll('[data-part=\"button\"]'))"
    ".filter(function (n) { return n.textContent.indexOf('Reset') >= 0; })[0]"
    ".click()"
)


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
def panel(monkeypatch):
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    monkeypatch.setenv("ACERVATOR_VARIANT", "react")
    from src.gui import variant_surface

    made = variant_surface.surface_class(variant_surface.FLEET_REPLAY)()
    made.resize(1100, 700)
    made.show()
    for _ in range(READY_ROUNDS):
        if made.page_ready:
            break
        settle(READY_STEP_MS)
    yield made
    made.hide()
    made.deleteLater()


def test_the_page_reports_no_fault_against_the_payload(panel):
    faults = json.loads(
        js(panel._web, "JSON.stringify(window.acervatorFleetReplay.faults())")
    )
    assert faults == [], faults


def test_a_status_write_reaches_the_status_line(panel):
    from src.gui.react_fleet_replay_panel import STATUS_TEXT_JS

    panel._status_error("venue down")
    settle(SETTLE_MS)
    assert js(panel._web, STATUS_TEXT_JS) == "venue down"


def test_a_loaded_fleet_draws_one_row_per_bot(panel):
    from src.gui.react_fleet_replay_panel import ROW_COUNT_JS

    assert js(panel._web, ROW_COUNT_JS) == 0, "the page drew a row before any load"
    panel._configs = list(CONFIGS)
    panel._populate_fleet_table()
    settle(SETTLE_MS)
    assert js(panel._web, ROW_COUNT_JS) == len(CONFIGS)


def test_a_press_on_the_page_runs_the_inherited_python(panel):
    seen: list = []
    original = type(panel)._on_reset_clicked

    def watched(self) -> None:
        seen.append(1)
        original(self)

    type(panel)._on_reset_clicked = watched
    try:
        js(panel._web, RESET_CLICK_JS)
        settle(SETTLE_MS)
    finally:
        type(panel)._on_reset_clicked = original
    assert seen, "the Reset press never reached the inherited Python"


def test_the_full_evaluation_switch_reaches_python_on_the_next_press(panel):
    before = panel._full_evaluation()
    js(panel._web, "document.querySelector('[data-part=\"switch\"]').click()")
    settle(SETTLE_MS)
    js(panel._web, RESET_CLICK_JS)
    settle(SETTLE_MS)
    assert panel._full_evaluation() is not before


def test_the_simulator_tab_builds_the_panel_the_variant_names(monkeypatch):
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    monkeypatch.setenv("ACERVATOR_VARIANT", "react")
    from src.gui.simulator_tab.simulator_tab import SimulatorTab

    tab = SimulatorTab()
    built = type(tab.fleet_replay).__name__
    tab.deleteLater()
    assert built == "FleetReplayReactPanel", built


def test_the_qt_variant_still_builds_the_qt_panel(monkeypatch):
    from PySide6.QtWidgets import QApplication, QTableWidget

    QApplication.instance() or QApplication([])
    monkeypatch.setenv("ACERVATOR_VARIANT", "qt")
    from src.gui import variant_surface

    made = variant_surface.surface_class(variant_surface.FLEET_REPLAY)()
    built, tables = type(made).__name__, len(made.findChildren(QTableWidget))
    made.deleteLater()
    assert built == "FleetReplayPanel", built
    assert tables == 1, tables
