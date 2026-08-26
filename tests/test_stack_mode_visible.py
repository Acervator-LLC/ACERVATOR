"""v3.23.28 — Stack Mode Visible-mode + Aggressive IOC-Limit + GUI tab pins.

Source-shape + minimal-stub tests. Full end-to-end wiring (real
exchange fills, live order-book placement) requires the sim
harness — pinned separately.
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ---------------------------------------------------------------------------
# OrderType.IOC_LIMIT — the enum must exist + connector must translate
# ---------------------------------------------------------------------------


class TestOrderTypeIOCLimit:
    def test_ioc_limit_enum_present(self):
        from src.exchange.base import OrderType

        assert hasattr(OrderType, "IOC_LIMIT")
        assert OrderType.IOC_LIMIT.value == "ioc_limit"

    def test_connector_translates_ioc_limit_to_limit_plus_tif(self):
        """ccxt connector must map IOC_LIMIT → create_order(type='limit',
        params={'timeInForce': 'IOC'})."""
        src = (REPO / "src" / "exchange" / "ccxt_connector.py").read_text(
            encoding="utf-8", errors="replace"
        )
        assert "OrderType.IOC_LIMIT" in src
        assert "timeInForce" in src and "IOC" in src
        assert (
            '_ccxt_type = "limit"' in src
        ), "IOC_LIMIT must map to native ccxt 'limit' + IOC time_in_force"


# ---------------------------------------------------------------------------
# Visible-mode Stack execution — source-shape pins
# ---------------------------------------------------------------------------


class TestVisibleModeSourceShape:
    @pytest.fixture(scope="class")
    def source(self) -> str:
        return (REPO / "src" / "trading" / "scrumming_bot.py").read_text(
            encoding="utf-8", errors="replace"
        )

    def test_open_stack_from_scrum_is_async(self, source):
        assert re.search(
            r"async def _open_stack_from_scrum\(", source
        ), "_open_stack_from_scrum must be async (v3.23.28)"

    def test_visible_mode_calls_guarded_place_order(self, source):
        """The Visible branch in _open_stack_from_scrum must place
        exchange orders via guarded_place_order per tranche."""
        m = re.search(
            r"async def _open_stack_from_scrum\([^)]*\)[^:]*:(.*?)(?=\n    async def |\n    def )",
            source,
            re.DOTALL,
        )
        assert m
        body = m.group(1)
        assert (
            "not self._invisible" in body or "_visible = not self._invisible" in body
        ), "Visible branch must detect not self._invisible"
        assert (
            "guarded_place_order" in body
        ), "Visible tranches must be placed via guarded_place_order"
        assert "OrderSide.SELL" in body

    def test_aggressive_selects_ioc_limit(self, source):
        m = re.search(
            r"async def _open_stack_from_scrum\([^)]*\)[^:]*:(.*?)(?=\n    async def |\n    def )",
            source,
            re.DOTALL,
        )
        body = m.group(1)
        assert (
            "OrderType.IOC_LIMIT" in body
        ), "Aggressive path must use OrderType.IOC_LIMIT"
        assert (
            "OrderType.LIMIT" in body
        ), "Non-aggressive Visible path must use OrderType.LIMIT"
        assert (
            "_aggressive" in body
        ), "Order type selection must gate on self._aggressive"

    def test_visible_reconciler_method_defined(self, source):
        assert "async def _reconcile_stack_tranches_visible(" in source

    def test_visible_reconciler_uses_get_open_orders(self, source):
        m = re.search(
            r"async def _reconcile_stack_tranches_visible\([^)]*\)[^:]*:(.*?)(?=\n    async def |\n    def )",
            source,
            re.DOTALL,
        )
        assert m
        body = m.group(1)
        assert (
            "get_open_orders" in body
        ), "Visible reconciler must call exchange.get_open_orders"
        assert (
            "get_order" in body
        ), "Visible reconciler must call get_order for terminal state"

    def test_visible_reconciler_marks_filled_and_cancelled(self, source):
        m = re.search(
            r"async def _reconcile_stack_tranches_visible\([^)]*\)[^:]*:(.*?)(?=\n    async def |\n    def )",
            source,
            re.DOTALL,
        )
        body = m.group(1)
        assert '"filled"' in body
        assert '"cancelled"' in body

    def test_tick_loop_wires_visible_reconciler(self, source):
        assert "await self._reconcile_stack_tranches_visible(" in source


# ---------------------------------------------------------------------------
# GUI: Stack Tranches tab
# ---------------------------------------------------------------------------


class TestStackTranchesTab:
    @pytest.fixture(scope="class")
    def source(self) -> str:
        return (REPO / "src" / "gui" / "bot_live_settings.py").read_text(
            encoding="utf-8", errors="replace"
        )

    def test_create_stack_tranches_tab_defined(self, source):
        assert "def _create_stack_tranches_tab(" in source

    def test_tab_registered_for_all_scrumming_bots(self, source):
        """v3.23.29 — tab registers on scrumming mode alone (no
        stack_mode sub-gate). Operator-reported 2026-07-25: the
        original sub-gate hid the tab entirely while the operator was
        inspecting the feature, defeating the reason to have it.
        Now mirrors Fold Tranches behaviour: always visible for
        scrumming bots; the empty-state message inside the tab body
        handles both 'stack_mode off' and 'no tranches yet' cases.

        RESTATED, issue #133 unit 7, and STRONGER. This was one regex
        over a literal `tabs.addTab(... "Stack Tranches")` under the
        scrumming gate. Registration now goes through
        `_install_stack_tranches_tab`, the mirror of the Fold tab's own
        installer, which also remembers the page so a clear can rebuild
        it in place. One regex over the old shape pinned the SPELLING;
        this follows the WIRING through both hops — the gate calls the
        installer, the installer adds the labelled tab and stores the
        handle — and `tests/test_fold_stack_ladder_symmetry.py` drives
        that installer against a real QTabWidget and reads the tab back
        off it. The invariant is unchanged: scrumming mode alone, no
        `stack_mode` sub-gate."""
        # Hop 1: the registration block is the scrumming gate calling
        # the installer, and nothing else.
        m = re.search(
            r'if\s+cfg\.mode\.value\s*==\s*"scrumming":\s*\n'
            r"\s*self\._install_stack_tranches_tab\(tabs\)",
            source,
        )
        assert m, (
            "Stack Tranches tab must register on scrumming mode alone "
            "(no stack_mode sub-gate)"
        )
        # Hop 2: the installer adds the labelled tab and keeps the page.
        body = re.search(
            r"def _install_stack_tranches_tab\([^)]*\)[^:]*:(.*?)"
            r"(?=\n        def |\n        async def )",
            source,
            re.DOTALL,
        )
        assert body, "_install_stack_tranches_tab body not found"
        assert "tabs.addTab(page, self.STACK_TRANCHES_TAB_LABEL)" in body.group(1)
        assert "self._stack_tab_page = page" in body.group(1)
        assert 'STACK_TRANCHES_TAB_LABEL = "Stack Tranches"' in source
        assert '"Stack Tranches"' in source

    def test_no_stack_mode_sub_gate_on_tab_registration(self, source):
        """Regression pin for the v3.23.29 fix. If any future edit
        re-adds a stack_mode gate around the Stack Tranches addTab
        call, catch it at test time."""
        m = re.search(
            r'and\s+getattr\(cfg,\s*"stack_mode"[^)]*\):\s*\n\s*tabs\.addTab\('
            r"[^)]*_create_stack_tranches_tab",
            source,
        )
        assert m is None, (
            "Stack Tranches tab registration re-acquired a stack_mode "
            "sub-gate. The tab must always register for scrumming bots "
            "so operators can find + inspect the feature. Empty-state "
            "message inside the tab body handles the stack_mode-off case."
        )

    def test_tab_reads_stack_tranches_ledger(self, source):
        m = re.search(
            r"def _create_stack_tranches_tab\(self\)[^:]*:(.*?)(?=\n        def )",
            source,
            re.DOTALL,
        )
        assert m
        body = m.group(1)
        assert "_stack_tranches" in body, "tab must read _bot._stack_tranches"
        assert "_stack_created" in body, "tab must read _bot._stack_created"

    def test_tab_surfaces_pending_filled_cancelled(self, source):
        m = re.search(
            r"def _create_stack_tranches_tab\(self\)[^:]*:(.*?)(?=\n        def )",
            source,
            re.DOTALL,
        )
        body = m.group(1)
        assert '"pending"' in body
        assert '"filled"' in body
        assert '"cancelled"' in body

    def test_tab_shows_visible_vs_invisible_mode_per_tranche(self, source):
        m = re.search(
            r"def _create_stack_tranches_tab\(self\)[^:]*:(.*?)(?=\n        def )",
            source,
            re.DOTALL,
        )
        body = m.group(1)
        assert "VISIBLE" in body and "INVISIBLE" in body


# ---------------------------------------------------------------------------
# Behavioural: async _open_stack_from_scrum in Invisible mode still works
# (regression check — 2B-2 tests already cover this but re-run under 2B-3)
# ---------------------------------------------------------------------------


class TestAsyncOpenStackRegression:
    def test_invisible_mode_populates_ledger_without_exchange(self):
        """Sanity: making the method async didn't break Invisible mode
        (no exchange call needed, no coroutine to await inside)."""
        from src.trading.scrumming_bot import ScrummingBot

        class _StubBus:
            def __init__(self):
                self.messages = []

            def emit(self, event, **kw):
                self.messages.append((event, kw))

        class _StubCfg:
            symbol = "BTC/USD"
            scrumming_interval_pct = 1.0
            trading_fee_pct = 0.6
            stack_tranche_count_target = 3
            split_distance_pct = 1.0
            stack_spacing_mode = "linear"
            stack_mode = True

        class _StubExI:
            min_order_size = 0.0

        class _StubBot:
            def __init__(self):
                self.bot_id = "stub"
                self.config = _StubCfg()
                self.exchange_interface = _StubExI()
                self._bus = _StubBus()
                self._stack_tranches = []
                self._stack_created = 0
                self._invisible = True  # Invisible → no exchange call
                self._aggressive = False

        bot = _StubBot()
        n = asyncio.run(
            ScrummingBot._open_stack_from_scrum(bot, scrum_price=100.0, scrum_size=30.0)
        )
        assert n == 3
        assert len(bot._stack_tranches) == 3
        # In Invisible mode, order_id should be None and visible=False
        for t in bot._stack_tranches:
            assert t["order_id"] is None
            assert t["visible"] is False
