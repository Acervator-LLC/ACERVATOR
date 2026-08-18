"""v3.23.75 — boot-smoke pin tests for ExchangeTab.

Regression fixture for the v3.23.74 → v3.23.75 boot crash:

    File "main.py", line 1154, in <module>
    File "main.py", line 616, in main
    File "src/gui/main_window.py", line 4999, in add_exchange_tab
        tab = ExchangeTab(exchange_id, display_name, ...)
    File "src/gui/main_window.py", line 2277, in __init__
        self._update_pull_rate_label)
    AttributeError: 'ExchangeTab' object has no attribute
    '_update_pull_rate_label'

Root cause: v3.23.74 added the ``_pull_rate_lbl`` widget + QTimer
inside ``ExchangeTab.__init__`` but placed the ``_update_pull_rate_label``
method on ``MainWindow`` (a different class). The timer bound to
``self._update_pull_rate_label`` where ``self`` = ExchangeTab, and
that attribute didn't exist. The .exe crashed at boot before the
main window even rendered.

The v3.23.74 pin tests didn't catch it because they only exercised
MarketDataPool directly (pure-Python) and never instantiated
ExchangeTab. This test closes that gap: it constructs an ExchangeTab
headless, fires the pull-rate timer once, and asserts the callback
completes without raising.

Any future addition of a QTimer.timeout.connect(self._xxx) will fail
this test if the method isn't on the class that owns the timer.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def test_exchange_tab_boot_does_not_crash(qapp):
    """ExchangeTab must construct without raising."""
    from src.gui.main_window import ExchangeTab
    tab = ExchangeTab(
        exchange_id="coinbase",
        exchange_name="Coinbase Test",
    )
    assert tab is not None
    tab.deleteLater()


def test_pull_rate_label_method_exists_on_exchange_tab(qapp):
    """v3.23.75 regression pin — the QTimer at ExchangeTab.__init__
    line ~2277 connects to self._update_pull_rate_label. That method
    MUST live on ExchangeTab (not MainWindow) or the timer fires
    against a missing attribute at every boot."""
    from src.gui.main_window import ExchangeTab
    assert hasattr(ExchangeTab, "_update_pull_rate_label"), (
        "ExchangeTab must define _update_pull_rate_label — the "
        "QTimer in __init__ binds to self._update_pull_rate_label. "
        "If this fires against a missing attribute the .exe crashes "
        "at boot (see v3.23.74 → v3.23.75 incident).")


def test_pull_rate_label_updates_without_raising(qapp):
    """Fire the label-update callback and confirm it survives an
    empty pool without raising."""
    from src.gui.main_window import ExchangeTab
    tab = ExchangeTab(
        exchange_id="coinbase",
        exchange_name="Coinbase Test",
    )
    # Direct call (bypasses QTimer scheduling for deterministic testing)
    tab._update_pull_rate_label()
    # Empty pool → label reports "idle" or "awaiting first fetch".
    # v3.23.76: text prefix changed from "Next data pull:" to
    # "Data pool:" — the countdown semantic was misleading under
    # passive on-demand coalescing (see data_pool.py:seconds_until
    # _next_pull docstring).
    txt = tab._pull_rate_lbl.text()
    assert "Data pool" in txt
    tab.deleteLater()
