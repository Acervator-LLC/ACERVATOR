"""v3.23.77 — pin the operator's canonical main-tab order.

Operator directive 2026-08-XX: default tab layout must be
Trading | Market Inspector | Bot Swarm | Asset Charts |
History | Simulator | Console

The reorder pass runs after all addTab/insertTab calls (see
main_window.py:_reorder_main_tabs). Any future tab addition that
isn't listed in CANONICAL_TAB_ORDER stays at the end — the caller
is free to add without editing the reorder list, but the operator
must update the list when they want a new tab to have a canonical
position.

This test binds the reorder helper to a synthetic QTabWidget so the
pin can run without booting the full MainWindow (which drags in
BotManager, event bus, splash timers, etc.).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import MethodType

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QLabel,
    QTabWidget,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def _bind_reorder_helper(tabs: QTabWidget) -> None:
    """Extract MainWindow._reorder_main_tabs as a plain callable and
    bind it to any object exposing ``self._main_tabs``. Keeps the
    test independent of MainWindow's full construction cost."""
    import src.gui.main_window as mw

    fn = mw.MainWindow.__dict__["_reorder_main_tabs"]

    class _Holder:
        pass

    holder = _Holder()
    holder._main_tabs = tabs
    holder._reorder = MethodType(fn, holder)
    return holder._reorder


def _make_tabs_in_wrong_order(qapp) -> QTabWidget:
    """Mirror the actual current addTab order in main_window.py so the
    pin test proves the reorder pass FIXES the ordering."""
    tabs = QTabWidget()
    tabs.addTab(QLabel("t"), "Trading")
    tabs.addTab(QLabel("c"), "Asset Charts")
    tabs.addTab(QLabel("b"), "Bot Swarm")
    tabs.addTab(QLabel("m"), "Market Inspector")
    tabs.insertTab(1, QLabel("s"), "Simulator")
    tabs.addTab(QLabel("h"), "History")
    tabs.addTab(QLabel("k"), "Console")
    return tabs


def test_reorder_produces_canonical_order(qapp):
    tabs = _make_tabs_in_wrong_order(qapp)
    reorder = _bind_reorder_helper(tabs)
    canonical = [
        "Trading",
        "Market Inspector",
        "Bot Swarm",
        "Asset Charts",
        "History",
        "Simulator",
        "Console",
    ]
    reorder(canonical)
    actual = [tabs.tabText(i) for i in range(tabs.count())]
    assert actual == canonical, f"tab order not canonical: {actual}"
    tabs.deleteLater()


def test_reorder_preserves_widgets(qapp):
    """moveTab must not destroy or swap widget instances."""
    tabs = _make_tabs_in_wrong_order(qapp)
    trading_widget_before = tabs.widget(0)
    reorder = _bind_reorder_helper(tabs)
    reorder(
        [
            "Trading",
            "Market Inspector",
            "Bot Swarm",
            "Asset Charts",
            "History",
            "Simulator",
            "Console",
        ]
    )
    assert tabs.tabText(0) == "Trading"
    assert tabs.widget(0) is trading_widget_before
    tabs.deleteLater()


def test_reorder_leaves_unnamed_tabs_at_end(qapp):
    """Tabs whose labels aren't in `desired` must keep their relative
    position at the end — future tab additions get a graceful default
    until the operator adds them to CANONICAL_TAB_ORDER."""
    tabs = QTabWidget()
    tabs.addTab(QLabel("a"), "Trading")
    tabs.addTab(QLabel("b"), "FutureTab")
    tabs.addTab(QLabel("c"), "History")
    reorder = _bind_reorder_helper(tabs)
    reorder(["Trading", "History"])
    labels = [tabs.tabText(i) for i in range(tabs.count())]
    assert labels[0] == "Trading"
    assert labels[1] == "History"
    assert "FutureTab" in labels
    tabs.deleteLater()


def test_reorder_is_idempotent(qapp):
    """Running the reorder twice must produce the same order (no
    swapping / no infinite churn)."""
    tabs = _make_tabs_in_wrong_order(qapp)
    reorder = _bind_reorder_helper(tabs)
    canonical = [
        "Trading",
        "Market Inspector",
        "Bot Swarm",
        "Asset Charts",
        "History",
        "Simulator",
        "Console",
    ]
    reorder(canonical)
    first_order = [tabs.tabText(i) for i in range(tabs.count())]
    reorder(canonical)
    second_order = [tabs.tabText(i) for i in range(tabs.count())]
    assert first_order == second_order == canonical
    tabs.deleteLater()
