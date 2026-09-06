"""The React gate status panel draws one row per bot and answers a gate write.

``PANE_ROW_COUNT_JS`` counts the rows the page drew and ``cell_for`` returns the
row a gate write goes through.
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
FLEET = ["BTC-USD", "ETH-USD", "SOL-USD"]
LAMP_STATES_JS = (
    "Array.from(document.querySelectorAll('[data-part=\"lamp\"]'))"
    ".map(function (n) { return n.getAttribute('data-state'); })"
    ".filter(function (v, i, a) { return a.indexOf(v) === i; }).sort()"
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
def pane(monkeypatch):
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    monkeypatch.setenv("ACERVATOR_VARIANT", "react")
    from src.gui import variant_surface

    made = variant_surface.surface_class(variant_surface.GATE_STATUS_PANEL)()
    made.resize(900, 400)
    made.show()
    for _ in range(READY_ROUNDS):
        if made.page_ready:
            break
        settle(READY_STEP_MS)
    yield made
    made.hide()
    made.deleteLater()


def rows(made) -> int:
    from src.gui.react_sim_visuals import PANE_ROW_COUNT_JS

    return int(js(made._web, PANE_ROW_COUNT_JS))


def test_a_pane_with_no_fleet_draws_no_row(pane):
    pane.set_symbols([])
    settle(SETTLE_MS)
    assert rows(pane) == 0, "the page drew a gate row for a pane holding none"


def test_a_loaded_pane_draws_one_row_for_every_bot(pane):
    pane.set_symbols(FLEET)
    settle(SETTLE_MS)
    assert rows(pane) == len(FLEET), f"the page drew {rows(pane)} of {len(FLEET)} rows"


def test_a_gate_write_changes_what_the_lights_show(pane):
    from src.gui.react_sim_visuals import PANE_LAMP_COUNT_JS

    pane.set_symbols(["BTC-USD"])
    settle(SETTLE_MS)
    assert int(js(pane._web, PANE_LAMP_COUNT_JS)) > 0, "the page drew no light"
    before = json.loads(js(pane._web, "JSON.stringify(" + LAMP_STATES_JS + ")"))
    pane.cell_for("BTC-USD").update_gates(
        scrum_armed=True,
        fold_armed=False,
        scrum_blockers=[],
        fold_blockers=["trend_hold"],
        landing_strip_side="scrum",
    )
    settle(SETTLE_MS)
    after = json.loads(js(pane._web, "JSON.stringify(" + LAMP_STATES_JS + ")"))
    assert after != before, f"the gate write left the lights at {before}"
    assert pane._pane.cell_for("BTC-USD").scrum_armed is True


def test_the_fleet_replay_panel_builds_the_pane_the_variant_names(monkeypatch):
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    monkeypatch.setenv("ACERVATOR_VARIANT", "react")
    from src.gui.simulator_tab.fleet.fleet_replay_panel import FleetReplayPanel

    made = FleetReplayPanel()
    built = type(made._gate_panel).__name__
    made.deleteLater()
    assert built == "GateStatusPanelReact", built


def test_the_qt_variant_still_builds_the_qt_pane(monkeypatch):
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    monkeypatch.setenv("ACERVATOR_VARIANT", "qt")
    from src.gui import variant_surface

    made = variant_surface.surface_class(variant_surface.GATE_STATUS_PANEL)()
    made.set_symbols(["BTC-USD", "ETH-USD"])
    built, held = type(made).__name__, made.symbols()
    made.deleteLater()
    assert built == "GateStatusPanel", built
    assert held == ["BTC-USD", "ETH-USD"], held
