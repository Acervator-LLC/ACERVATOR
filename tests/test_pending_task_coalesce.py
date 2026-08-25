"""v3.23.59 — pin tests for _cancel_if_pending helper + source
discipline for the two coalesced call sites (chart fetch, scout
refresh). Confirms the pending-task-destruction warnings from prior
crash logs stay silenced."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


class TestCancelIfPendingHelper:
    """The helper is a staticmethod on CryptoMainWindow. Test it via
    its class attribute so we don't need a QApplication."""

    def _get_helper(self):
        pytest.importorskip("PySide6.QtWidgets")
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        _app = QApplication.instance() or QApplication([])
        from src.gui.main_window import MainWindow

        return MainWindow._cancel_if_pending

    def test_none_is_safe(self):
        h = self._get_helper()
        h(None)  # must not raise

    def test_done_future_left_alone(self):
        h = self._get_helper()
        fut = SimpleNamespace(
            done=lambda: True,
            cancel=lambda: (_ for _ in ()).throw(
                AssertionError("cancel called on done future")
            ),
        )
        h(fut)  # must not call cancel

    def test_pending_future_is_cancelled(self):
        h = self._get_helper()
        state = {"cancelled": False}

        def _cancel():
            state["cancelled"] = True
            return True

        fut = SimpleNamespace(done=lambda: False, cancel=_cancel)
        h(fut)
        assert state["cancelled"] is True

    def test_exception_swallowed(self):
        h = self._get_helper()
        fut = SimpleNamespace(
            done=lambda: False,
            cancel=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        h(fut)  # must swallow


class TestCoalesceSourceDiscipline:
    """v3.23.59 — assert the two known task-leak sources are wired
    through _cancel_if_pending + _pending_* slots. Guards against a
    regression to the pre-v3.23.59 fire-and-forget pattern that
    produced 'Task was destroyed but pending' warnings at shutdown."""

    def _src(self) -> str:
        p = REPO / "src" / "gui" / "main_window.py"
        return p.read_text(encoding="utf-8")

    def test_chart_fetch_uses_pending_slot(self):
        src = self._src()
        assert "_pending_chart_fetch" in src, (
            "Chart-fetch pump lost its coalescing slot — the "
            "'Task was destroyed but pending' warnings for "
            "TradeChartsTab.fetch_chart_data will return."
        )
        assert (
            "_cancel_if_pending" in src
        ), "Coalescing helper _cancel_if_pending removed."

    def test_scout_refresh_uses_pending_slot(self):
        src = self._src()
        assert "_pending_scout_refresh" in src, (
            "MarketPairsScout pump lost its coalescing slot — the "
            "'Task was destroyed but pending' warning for "
            "MarketPairsScout.refresh_from_connectors will return."
        )


class TestShutdownDrain:
    def test_main_drains_pending_tasks_before_loop_close(self):
        """main.py must cancel + await pending tasks before
        loop.close() so shutdown emits no 'destroyed pending'
        warnings even for tasks that weren't caught by the
        _pending_* slots (per-bot ticks etc.)."""
        p = REPO / "main.py"
        src = p.read_text(encoding="utf-8")
        # Order: asyncio.all_tasks → cancel → gather → loop.close
        idx_all = src.find("asyncio.all_tasks(loop)")
        idx_cancel_all = src.find("_t.cancel()")
        idx_gather = src.find("asyncio.gather(*_pending")
        # rfind — the ACTUAL loop.close() call is the last one, after
        # the drain block. The earlier mention is inside a comment.
        idx_close = src.rfind("loop.close()")
        assert (
            0 < idx_all < idx_cancel_all < idx_gather < idx_close
        ), "Shutdown-drain block missing or out of order."
