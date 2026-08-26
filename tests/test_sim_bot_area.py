"""The Simulator's bot area IS the Trading Tab's bot table.

Operator task 2026-08-08 (screenshot area 5): "Needs to be redesigned to
match the Trading Tab's bot area." Plus, added the same day: "Add a drop
down menu for active simulator bots."

NOT A NEW TABLE. `BotStatusTable` already renders the columns the
operator pointed at -- Bot ID, Symbol, Mode, Trades, Target, Target BTC,
Target ETH, Ammo, Fire, Detail -- with the header dots, the state
colouring and the Ammo arithmetic. Rebuilding that in the Simulator
would be the `FleetSimExchange` mistake a second time: a copy of
something that already exists, certain to drift from it. The sim mounts
the SAME CLASS and feeds it through an adapter.

THE IMPORT IS DEFERRED ON PURPOSE. `main_window` imports
`simulator_tab` (main_window.py:3971), so a module-scope import back
the other way is a cycle. `SimulatorTab` is only ever constructed BY
`main_window`, so resolving the class inside a method is safe -- and
returning None when it cannot be resolved keeps a headless import of
this panel a legitimate caller.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(autouse=True)
def _destroy_widgets():
    """Delete top-level widgets after each test; unparented Qt widgets
    accumulate for the life of the process and segfault a long run."""
    yield
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:  # pragma: no cover
        return
    app = QApplication.instance()
    if app is None:
        return
    for w in list(app.topLevelWidgets()):
        w.hide()
        w.setParent(None)
        w.deleteLater()
    app.processEvents()


SYMS = ["CHIP/USD", "SPK/USD", "XRP/USD"]
T0 = 1_776_778_500_000
STEP = 300_000


def _qapp():
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:  # pragma: no cover
        pytest.skip("PySide6 unavailable")
    return QApplication.instance() or QApplication([])


def _rows(n=300, px0=1.0):
    out, px = [], px0
    for i in range(n):
        px *= 1.0 + ((i % 5) - 2) * 0.003
        out.append([T0 + i * STEP, px, px * 1.004, px * 0.996, px, 70.0])
    return out


def _controller():
    from src.simulator.fleet.fleet_replay_controller import (
        FleetReplayController,
    )

    cfgs = [
        {
            "mode": "scrumming",
            "symbol": s,
            "target_balance": 100.0,
            "target_asset": s.split("/")[0],
            "base_currency": "USD",
            "_src_bot_id": f"bot{i:04d}",
        }
        for i, s in enumerate(SYMS)
    ]
    ctl = FleetReplayController(
        configs=cfgs,
        candles_by_symbol={s: _rows() for s in SYMS},
        smart_wires=[],
        tick_delay_s=0.0,
        max_candles=50,
        activity_log_cb=lambda *_: None,
        performance_log_cb=lambda *_: None,
    )
    ctl._build_sim()
    for _ in range(120):
        ctl._tape.step()
    return ctl


def _panel_with_fleet():
    _qapp()
    from src.gui.simulator_tab.fleet.fleet_replay_panel import FleetReplayPanel

    p = FleetReplayPanel()
    p._controller = _controller()
    return p


def _tab():
    _qapp()
    import src.gui.main_window  # noqa: F401 - as the real app has it
    from src.gui.simulator_tab.simulator_tab import SimulatorTab

    t = SimulatorTab()
    t.resize(1600, 900)
    return t


class TestTheAdapterMatchesTheTableContract:
    def test_one_status_per_bot(self):
        p = _panel_with_fleet()
        assert len(p.sim_bot_statuses()) == len(p._controller._bots)

    def test_every_key_update_bots_reads_is_present(self):
        """Read off `BotStatusTable.update_bots`. A missing key does not
        raise there -- `.get()` returns None and the cell renders
        wrong -- so the contract is checked here instead."""
        p = _panel_with_fleet()
        for st in p.sim_bot_statuses():
            for k in (
                "bot_id",
                "symbol",
                "mode",
                "state",
                "exchange",
                "target_balance",
                "live_target_balance",
                "current_holdings",
                "quote_to_usd",
                "stats",
            ):
                assert k in st, k
            for k in ("current_price", "position_value"):
                assert k in st["stats"], k

    def test_bot_ids_are_the_simulated_ones(self):
        p = _panel_with_fleet()
        for st in p.sim_bot_statuses():
            assert st["bot_id"].startswith("simulated_")

    def test_position_value_is_holdings_times_price(self):
        p = _panel_with_fleet()
        for st in p.sim_bot_statuses():
            expected = st["current_holdings"] * st["stats"]["current_price"]
            assert st["stats"]["position_value"] == pytest.approx(expected)

    def test_price_comes_from_the_tape(self):
        """A zero price would make Ammo read as the whole target on
        every row, which looks like a fleet that has never bought."""
        p = _panel_with_fleet()
        assert all(st["stats"]["current_price"] > 0 for st in p.sim_bot_statuses())

    def test_no_controller_yields_no_rows_rather_than_raising(self):
        _qapp()
        from src.gui.simulator_tab.fleet.fleet_replay_panel import FleetReplayPanel

        assert FleetReplayPanel().sim_bot_statuses() == []


class TestItIsTheTradingTabsTable:
    def test_the_mounted_class_is_bot_status_table(self):
        t = _tab()
        assert t.mount_bot_status_table() is True
        w = t.fleet_replay._bot_status_table_widget
        assert type(w).__name__ == "BotStatusTable"

    def test_it_is_the_very_same_class_main_window_uses(self):
        """Not a look-alike."""
        t = _tab()
        t.mount_bot_status_table()
        from src.gui.main_window import BotStatusTable

        assert isinstance(t.fleet_replay._bot_status_table_widget, BotStatusTable)

    def test_the_columns_are_the_trading_tabs_columns(self):
        t = _tab()
        t.mount_bot_status_table()
        from src.gui.main_window import BotStatusTable

        assert list(BotStatusTable.COLUMNS) == [
            "Bot ID",
            "Symbol",
            "Mode",
            "Trades",
            "Target",
            "Target BTC",
            "Target ETH",
            "Ammo",
            "Fire",
            "",
        ]

    def test_mounting_twice_does_not_stack_two_tables(self):
        t = _tab()
        assert t.mount_bot_status_table() is True
        first = t.fleet_replay._bot_status_table_widget
        assert t.mount_bot_status_table() is True
        assert t.fleet_replay._bot_status_table_widget is first

    def test_the_fleet_fills_the_rows(self):
        t = _tab()
        t.mount_bot_status_table()
        t.fleet_replay._controller = _controller()
        st = t.fleet_replay.sim_bot_statuses()
        w = t.fleet_replay._bot_status_table_widget
        w.update_bots(st)
        assert w.rowCount() == len(SYMS)
        assert w.columnCount() == 10


class TestTheActiveBotDropdown:
    def test_it_exists_and_defaults_to_all(self):
        t = _tab()
        assert t._active_bot_picker is not None
        assert t.active_bot_id() == ""

    def test_it_lists_every_loaded_bot(self):
        t = _tab()
        t.fleet_replay._controller = _controller()
        t.refresh_active_bot_roster()
        assert t._active_bot_picker.count() == len(SYMS) + 1

    def test_selecting_one_returns_its_id(self):
        t = _tab()
        t.fleet_replay._controller = _controller()
        t.refresh_active_bot_roster()
        t._active_bot_picker.setCurrentIndex(1)
        assert t.active_bot_id().startswith("simulated_")

    def test_it_and_the_table_are_built_from_one_source(self):
        """Two lists from two sources is how they end up disagreeing."""
        t = _tab()
        t.mount_bot_status_table()
        t.fleet_replay._controller = _controller()
        st = t.fleet_replay.sim_bot_statuses()
        t.fleet_replay._bot_status_table_widget.update_bots(st)
        t.refresh_active_bot_roster(st)
        ids = {
            t._active_bot_picker.itemData(i)
            for i in range(1, t._active_bot_picker.count())
        }
        assert ids == {s["bot_id"] for s in st}

    def test_a_reload_keeps_the_selection(self):
        t = _tab()
        t.fleet_replay._controller = _controller()
        t.refresh_active_bot_roster()
        t._active_bot_picker.setCurrentIndex(2)
        keep = t.active_bot_id()
        t.refresh_active_bot_roster()
        assert t.active_bot_id() == keep

    def test_an_empty_fleet_leaves_only_all_bots(self):
        t = _tab()
        t.refresh_active_bot_roster([])
        assert t._active_bot_picker.count() == 1
        assert t.active_bot_id() == ""


class TestTheRenderIsReported:
    def test_the_emitter_reports_rows_against_bots(self):
        from src.core.signal_contract import SignalSink, reset_throttle, set_sink

        sink = SignalSink(flush_every=10_000)
        set_sink(sink)
        reset_throttle()
        try:
            p = _panel_with_fleet()
            st = p.sim_bot_statuses()
            p.emit_bot_table(len(st))
            rec = sink.records("sim.06.010.postcondition.bot_table.rendered")[0]
            assert rec.ok is True
            assert rec.actual == rec.expected == len(SYMS)
        finally:
            set_sink(None)
            reset_throttle()

    def test_a_dropped_row_reports_false(self):
        """NEGATIVE CONTROL -- an adapter that skips a bot must not
        look identical to one that renders them all."""
        from src.core.signal_contract import SignalSink, reset_throttle, set_sink

        sink = SignalSink(flush_every=10_000)
        set_sink(sink)
        reset_throttle()
        try:
            p = _panel_with_fleet()
            p.emit_bot_table(len(SYMS) - 1)
            assert (
                sink.records("sim.06.010.postcondition.bot_table.rendered")[0].ok
                is False
            )
        finally:
            set_sink(None)
            reset_throttle()
