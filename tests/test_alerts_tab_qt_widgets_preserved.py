"""The Qt Notifications and Alerts tab still holds every widget it paints.

`src/gui/web/alerts_tab.js` draws the same tab in the renderer from the
`alerts_tab.state` payload. The Qt widget stays reachable and whole until
the operational logs verify that panel, so this file counts the live
children of one real `AlertsTab` and fails when one goes out of
`src/gui/alerts_tab.py`.

The census is read off a constructed widget, never off the source text,
so a refactor that moves the tab keeps passing and a widget that stops
being built does not.

FALSIFICATION
=============
Wrong if `census` returns the same counts for a tab a widget was taken
out of, when nothing here could report a removal.
`test_the_census_reports_a_button_taken_out_of_the_tab` is that control:
it takes one button off a built tab and requires the count to drop.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui import alerts_tab as shipped
from src.gui.main_tabs import alerts_tab_surface as surface

#: Two routed events and three messages, so the two tables differ in height.
MANAGER_SPEC: dict = {
    "config": {
        "telegram_configured": True,
        "sms_configured": False,
        "rules": {
            "trade_filled": {
                "priority": "high",
                "channels": ["IN_APP", "TELEGRAM"],
            },
            "risk_breach": {"priority": "critical", "channels": ["SOUND"]},
        },
    },
    "history": [
        {
            "timestamp": time.time(),
            "priority": "critical",
            "title": "Drawdown",
            "message": "the ceiling was reached",
            "channels_sent": ["IN_APP"],
            "acknowledged": False,
        },
        {
            "timestamp": time.time(),
            "priority": "low",
            "title": "Filled",
            "message": "a scrum completed",
            "channels_sent": ["IN_APP", "TELEGRAM"],
            "acknowledged": True,
        },
        {
            "timestamp": time.time(),
            "priority": "medium",
            "title": "Routed",
            "message": "a message reached Telegram",
            "channels_sent": ["TELEGRAM"],
            "acknowledged": True,
        },
    ],
    "unread": 1,
}

#: The live children one refreshed tab holds, by the class that builds them.
EXPECTED_CENSUS: dict = {
    "QSplitter": 1,
    "QGroupBox": 4,
    "QTableWidget": 2,
    "QPushButton": 3,
    "QLineEdit": 3,
}

WIDGETS_HELD: list = []


def qt_classes() -> dict:
    """Every class the census counts, by the name this file calls it."""
    from PySide6.QtWidgets import (
        QGroupBox,
        QLineEdit,
        QPushButton,
        QSplitter,
        QTableWidget,
    )

    return {
        "QSplitter": QSplitter,
        "QGroupBox": QGroupBox,
        "QTableWidget": QTableWidget,
        "QPushButton": QPushButton,
        "QLineEdit": QLineEdit,
    }


def census(tab: Any) -> dict:
    """How many live children of each counted class `tab` holds."""
    return {
        name: len(tab.findChildren(found)) for name, found in qt_classes().items()
    }


def refreshed_tab() -> Any:
    """One real AlertsTab driven over the manager, held against collection."""
    from tests.qt_pixel import ensure_app

    ensure_app()
    tab = shipped.AlertsTab(surface.build_manager(MANAGER_SPEC))
    WIDGETS_HELD.append(tab)
    tab.refresh()
    return tab


def test_the_alerts_tab_holds_every_widget_it_ships():
    found = census(refreshed_tab())
    assert found == EXPECTED_CENSUS, f"the Qt Alerts tab now holds {found}"


def test_the_alerts_tab_names_the_four_group_boxes_it_paints():
    from PySide6.QtWidgets import QGroupBox

    tab = refreshed_tab()
    titles = {group.title() for group in tab.findChildren(QGroupBox)}
    assert titles == {
        surface.TELEGRAM_GROUP_TITLE,
        surface.SMS_GROUP_TITLE,
        surface.RULES_GROUP_TITLE,
        surface.HISTORY_GROUP_TITLE,
    }, f"the Qt Alerts tab now titles its groups {sorted(titles)}"


def test_the_alerts_tab_names_the_three_buttons_it_paints():
    from PySide6.QtWidgets import QPushButton

    tab = refreshed_tab()
    words = {found.text() for found in tab.findChildren(QPushButton)}
    assert words == {
        surface.TEST_BUTTON_TEXT,
        surface.SAVE_BUTTON_TEXT,
        surface.ACK_BUTTON_TEXT,
    }, f"the Qt Alerts tab now names its buttons {sorted(words)}"


def test_the_alerts_tab_fills_one_row_for_each_event_and_each_message():
    from PySide6.QtWidgets import QTableWidget

    tab = refreshed_tab()
    rules, history = tab.findChildren(QTableWidget)
    wanted_rules = len(MANAGER_SPEC["config"]["rules"])
    wanted_history = len(MANAGER_SPEC["history"])
    assert wanted_rules != wanted_history, (
        "both tables were driven to the same height, so this test cannot "
        "tell one from the other"
    )
    assert rules.rowCount() == wanted_rules, (
        f"{wanted_rules} events reported but {rules.rowCount()} rows filled"
    )
    assert history.rowCount() == wanted_history, (
        f"{wanted_history} messages reported but "
        f"{history.rowCount()} rows filled"
    )


def test_the_census_reports_a_button_taken_out_of_the_tab():
    from PySide6.QtWidgets import QPushButton

    tab = refreshed_tab()
    before = census(tab)
    taken = tab.findChildren(QPushButton)[0]
    taken.setParent(None)
    WIDGETS_HELD.append(taken)
    after = census(tab)
    assert after["QPushButton"] == before["QPushButton"] - 1, (
        "the census cannot see a widget leave the tab: "
        f"{before} before, {after} after one button was taken out"
    )
