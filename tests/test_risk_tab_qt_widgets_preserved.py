"""The Qt Risk tab still holds every widget it paints.

`src/gui/web/risk_tab.js` draws the same tab in the renderer from the
`risk_tab.state` payload. The Qt widget stays reachable and whole until
the operational logs verify that panel, so this file counts the live
children of one real `RiskTab` and fails when one goes out of
`src/gui/risk_tab.py`.

The census is read off a constructed widget, never off the source text,
so a refactor that moves the tab keeps passing and a widget that stops
being built does not.

FALSIFICATION
=============
Wrong if `census` returns the same counts for a tab a widget was taken
out of, when nothing here could report a removal.
`test_the_census_reports_a_group_box_taken_out_of_the_tab` is that
control: it takes one group box off a built tab and requires the count
to drop.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui import risk_tab as shipped
from src.gui.main_tabs import risk_tab_surface as surface

#: Two assets and two exchanges, so every bar stack grows more than one.
MANAGER_SPEC: dict = {
    "status": {
        "drawdown_pct": 12.0,
        "peak_pnl": 400.0,
        "total_exposure": 1000.0,
        "critical_alerts": 1,
        "alerts_1h": 2,
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
            "timestamp": 0.0,
            "severity": "critical",
            "rule_name": "max_drawdown",
            "message": "drawdown past its ceiling",
            "action_taken": "halt",
        }
    ],
}

#: The live children one refreshed tab holds, by the class that builds them.
EXPECTED_CENSUS: dict = {
    "QSplitter": 1,
    "QGroupBox": 4,
    "QTableWidget": 2,
    "DrawdownGauge": 1,
    "ExposureBar": 4,
    "QProgressBar": 4,
}

WIDGETS_HELD: list = []


def qt_classes() -> dict:
    """Every class the census counts, by the name this file calls it."""
    from PySide6.QtWidgets import (
        QGroupBox,
        QProgressBar,
        QSplitter,
        QTableWidget,
    )

    return {
        "QSplitter": QSplitter,
        "QGroupBox": QGroupBox,
        "QTableWidget": QTableWidget,
        "DrawdownGauge": shipped.DrawdownGauge,
        "ExposureBar": shipped.ExposureBar,
        "QProgressBar": QProgressBar,
    }


def census(tab: Any) -> dict:
    """How many live children of each counted class `tab` holds."""
    return {name: len(tab.findChildren(found)) for name, found in qt_classes().items()}


def refreshed_tab() -> Any:
    """One real RiskTab driven over the manager, held against collection."""
    from tests.qt_pixel import ensure_app

    ensure_app()
    tab = shipped.RiskTab(surface.build_manager(MANAGER_SPEC))
    WIDGETS_HELD.append(tab)
    tab.refresh()
    return tab


def test_the_risk_tab_holds_every_widget_it_ships():
    found = census(refreshed_tab())
    assert found == EXPECTED_CENSUS, f"the Qt Risk tab now holds {found}"


def test_the_risk_tab_names_the_four_group_boxes_it_paints():
    from PySide6.QtWidgets import QGroupBox

    tab = refreshed_tab()
    titles = {group.title() for group in tab.findChildren(QGroupBox)}
    assert titles == {
        surface.ASSET_GROUP_TITLE,
        surface.EXCHANGE_GROUP_TITLE,
        surface.ALERTS_GROUP_TITLE,
        surface.RULES_GROUP_TITLE,
    }, f"the Qt Risk tab now titles its groups {sorted(titles)}"


def test_the_risk_tab_grows_one_exposure_bar_for_each_holding():
    tab = refreshed_tab()
    snapshot = MANAGER_SPEC["snapshots"][0]
    wanted = len(snapshot["asset_exposures"]) + len(snapshot["exchange_exposures"])
    found = len(tab.findChildren(shipped.ExposureBar))
    assert found == wanted, f"{wanted} holdings reported but {found} bars were built"


def test_the_census_reports_a_group_box_taken_out_of_the_tab():
    from PySide6.QtWidgets import QGroupBox

    tab = refreshed_tab()
    before = census(tab)
    taken = tab.findChildren(QGroupBox)[0]
    taken.setParent(None)
    WIDGETS_HELD.append(taken)
    after = census(tab)
    assert after["QGroupBox"] == before["QGroupBox"] - 1, (
        "the census cannot see a widget leave the tab: "
        f"{before} before, {after} after one group box was taken out"
    )
