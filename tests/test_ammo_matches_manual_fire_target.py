"""The Ammo readout and Manual Fire must mean the same target.

OPERATOR REPORT
"Manual fire is not re-zeroing the bot to the Target Balance as expected
and required. I am seeing strange, intermittent and hard to explain
amounts being transacted."

THE MECHANISM
The Ammo cell read `status["target_balance"]`, which `get_status` fills
from `config.target_balance` -- the operator's INPUT, frozen, and never
moved by compounding.

`_execute_manual_rebalance` sizes its trade from
`delta_usd = current_value - self._target_balance`: the LIVE grown value.

So the readout measured distance to one target and the button re-zeroed
to another. The trade differed from the displayed Ammo by exactly the
accrued growth.

WHY IT LOOKED INTERMITTENT
Measured against live state 2026-08-06: 26 of 35 bots carried accrued
growth and were mismatched; 9 carried none and behaved perfectly. So the
same button was correct on some bots and wrong on others with no visible
pattern. Largest gap CAP/USD, $5.41 against a $50 target -- 10.83%.

    SYMBOL      GUI showed   engine used   gap
    CAP/USD         50.00         55.41   +5.41   (10.83%)
    BILL/USD       250.00        253.10   +3.10
    GROVE/USD      100.00        102.61   +2.61
    ...
    RAVE/USD        50.00         50.00   +0.00   (never compounded)

WHICH ONE IS CORRECT
The engine. The operator's stated invariant is that compounding is the
only mechanism besides a user edit permitted to move Target Balance --
so the bot SHOULD trade against the grown value, and the display was the
side that was wrong. This is a display-only change: no order size, no
order timing, and no engine path is touched.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.trading.scrumming_bot import ScrummingBot  # noqa: E402

AMMO_COLUMN = 7
TARGET_COLUMN = 4

CONFIG_TARGET = 50.00
LIVE_TARGET = 55.41
POSITION_VALUE = 60.00


def _table():
    """One real BotStatusTable on the process application object."""
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtWidgets import QApplication

    from src.gui.widgets.bot_status_table import BotStatusTable

    QApplication.instance() or QApplication([])
    return BotStatusTable()


def _status(**overrides) -> dict:
    """One scrumming status in the shape ExchangeTab hands update_bots."""
    found = {
        "bot_id": "bot-ammo-0001",
        "symbol": "CAP/USD",
        "mode": "scrumming",
        "state": "RUNNING",
        "exchange": "test",
        "current_holdings": 1.0,
        "quote_to_usd": 1.0,
        "target_balance": CONFIG_TARGET,
        "live_target_balance": LIVE_TARGET,
        "stats": {
            "position_value": POSITION_VALUE,
            "current_price": POSITION_VALUE,
            "total_trades": 0,
        },
    }
    found.update(overrides)
    return found


def _ammo_text(target_val: float) -> str:
    """The Ammo text ``_compose_ammo_cell`` writes for one target."""
    from src.gui.table_cells import _compose_ammo_cell

    return _compose_ammo_cell(
        stats_pv=POSITION_VALUE,
        holdings=1.0,
        cur_price=POSITION_VALUE,
        qrate=1.0,
        target_val=target_val,
    )["text"]


def _cell(status, column) -> str:
    """The text one column shows for one status, off the real table."""
    table = _table()
    table.update_bots([status])
    item = table.item(0, column)
    assert item is not None, f"the table painted no cell at column {column}"
    return item.text()


class TestTheDisplayMeasuresAgainstTheEngineTarget:
    def test_the_ammo_cell_is_the_gap_to_the_live_target(self):
        assert _cell(_status(), AMMO_COLUMN) == _ammo_text(LIVE_TARGET), (
            "the Ammo cell is measured against config.target_balance "
            "while Manual Fire re-zeroes to the live grown target"
        )

    def test_the_config_target_paints_a_different_ammo_cell(self):
        """POSITIVE CONTROL: LIVE_TARGET and CONFIG_TARGET reach
        different Ammo text."""
        assert _cell(_status(), AMMO_COLUMN) != _ammo_text(CONFIG_TARGET)

    def test_a_bot_without_the_live_key_falls_back_to_the_configured_one(self):
        """A status carrying no ``live_target_balance`` renders against
        ``target_balance``, not against 0.00."""
        without_live = _status()
        without_live.pop("live_target_balance")
        assert _cell(without_live, AMMO_COLUMN) == _ammo_text(CONFIG_TARGET)

    def test_the_target_column_shows_the_live_target_too(self):
        """The Target cell sits beside the Ammo cell and reads the same
        ``live_target_balance``."""
        assert _cell(_status(), TARGET_COLUMN) == f"${LIVE_TARGET:.4f}"


class _Ticker:
    def __init__(self, last):
        self.last = last


class _Bus:
    def __init__(self):
        self.messages: list[dict] = []

    def emit(self, _event, **kwargs):
        self.messages.append(dict(kwargs))


class _Stats:
    total_trades = 0
    total_sells = 0
    total_buys = 0
    trade_volume = 0.0
    last_trade_time = 0.0
    ytd_scrummed_usd = 0.0
    total_scrummed_usd = 0.0
    total_folded_usd = 0.0
    ytd_folded_usd = 0.0


class _Order:
    id = "manual-fire-order-1"

    def __init__(self, price):
        self.average = price
        self.price = price


def _fire_bot(cfg_target: float, live_target: float, position_value: float):
    """A bot running the REAL ``_execute_manual_rebalance``.

    ``_target_balance`` carries the grown target and ``config.target_balance``
    the operator's frozen input, so the placed order names which one sized it.
    """
    price = position_value
    bot: Any = object.__new__(ScrummingBot)
    bot.bot_id = "bot-ammo-0001"
    bot.placed = []
    bot._bus = _Bus()
    bot.config = type(
        "C",
        (),
        {
            "symbol": "CAP/USD",
            "target_asset": "CAP",
            "base_currency": "USD",
            "exchange_id": "test",
            "scrumming_interval_pct": 1.0,
            "trading_fee_pct": 0.6,
            "target_balance": cfg_target,
            "max_target_growth_pct": 100.0,
            "position_ceiling_enabled": False,
            "profit_folding_active": False,
        },
    )()
    bot.stats = _Stats()
    bot._current_holdings = 1.0
    bot._main_lots = [{"units": 1.0, "initial_buy_price": price}]
    bot._fold_tranches = []
    bot._fold_queue_usd = 0.0
    bot._fold_cycle_cap_consumed = 0.0
    bot._standing_surplus_usd = 0.0
    bot._retained_this_cycle_usd = 0.0
    bot._fold_accumulator = 0.0
    bot._target_grow_last_side = None
    bot._tranches_closed_lifetime = 0
    bot._tranches_created_lifetime = 0
    bot._tranches_malformed_dropped = 0
    bot._pending_wire_credits = 0.0
    bot._last_trade_side = None
    bot._last_trade_price = 0.0
    bot._last_bb = None
    bot._quote_to_usd = 1.0
    bot._manual_fire_pending = True
    bot._target_balance = live_target
    bot._anchor_target_balance = live_target

    async def _refresh():
        return 1.0

    async def _place(**kwargs):
        bot.placed.append(dict(kwargs))
        return _Order(price)

    async def _settled(order, symbol_, requested, tick_price):
        del order, symbol_, tick_price
        return requested, price, True

    async def _balance(currency):
        units = 1.0 if currency == "CAP" else 1_000_000.0
        return type("B", (), {"total": units, "free": units, "absent": False})()

    def _ignore(*args, **kwargs):
        del args, kwargs

    def _zero(*args, **kwargs):
        del args, kwargs
        return 0.0

    bot._refresh_quote_to_usd = _refresh
    bot.guarded_place_order = _place
    bot._settled_fill = _settled
    bot._get_balance = _balance
    bot._emit_voting_panel_snapshot_at_fire = _ignore
    bot._emit_gate_decision_at_fire = _ignore
    bot._reset_opposing_hysteresis_after_fill = _ignore
    bot._route_scrum_proceeds_via_wires = _zero
    bot.note_scrum_retention_usd = _ignore
    return bot


def _engine_delta(cfg: float, live: float, pos: float) -> float:
    """Signed USD the real Manual Fire path transacts, sell positive."""
    bot = _fire_bot(cfg, live, pos)
    asyncio.run(bot._execute_manual_rebalance(_Ticker(pos), "manual_button"))
    if not bot.placed:
        return 0.0
    order = bot.placed[-1]
    side = order["side"]
    signed = 1.0 if getattr(side, "value", side) == "sell" else -1.0
    return signed * float(order["amount"]) * pos


class TestTheArithmeticAgrees:
    """The property that matters: for the same position, the Ammo and
    the manual-rebalance delta must be the same number."""

    @pytest.mark.parametrize(
        "cfg,live,pos",
        [
            (50.00, 55.41, 60.00),  # CAP/USD, the worst live mismatch
            (250.00, 253.10, 240.00),  # BILL/USD, fold side
            (50.00, 50.00, 55.00),  # RAVE/USD, never compounded
            (100.00, 102.61, 102.61),  # exactly at the live target
        ],
    )
    def test_display_delta_equals_engine_delta(self, cfg, live, pos):
        from src.gui.table_cells import _compose_ammo_cell

        cell = _compose_ammo_cell(
            stats_pv=pos, holdings=1.0, cur_price=pos, qrate=1.0, target_val=live
        )
        engine = _engine_delta(cfg, live, pos)
        assert cell["delta"] == pytest.approx(engine, abs=0.01), (
            f"Ammo shows {cell['delta']:+.4f} but Manual Fire "
            f"transacted {engine:+.4f}"
        )

    def test_the_config_target_would_size_a_different_order(self):
        """POSITIVE CONTROL: ``_execute_manual_rebalance`` transacts a
        different amount for CONFIG_TARGET than for LIVE_TARGET."""
        against_live = _engine_delta(CONFIG_TARGET, LIVE_TARGET, POSITION_VALUE)
        against_config = _engine_delta(CONFIG_TARGET, CONFIG_TARGET, POSITION_VALUE)
        assert against_live != pytest.approx(against_config)
        assert abs(against_live - against_config) == pytest.approx(5.41, abs=0.01)

    def test_a_bot_at_its_live_target_transacts_nothing(self):
        """Manual Fire re-zeroes the bot, so a re-zeroed bot places no
        order on the next fire."""
        bot = _fire_bot(100.00, 102.61, 102.61)
        asyncio.run(bot._execute_manual_rebalance(_Ticker(102.61), "manual_button"))
        assert bot.placed == [], f"a re-zeroed bot still traded {bot.placed}"

    def test_a_bot_away_from_its_live_target_does_trade(self):
        """POSITIVE CONTROL for the no-op above: the same rig places an
        order once the position leaves the live target."""
        bot = _fire_bot(100.00, 102.61, 120.00)
        asyncio.run(bot._execute_manual_rebalance(_Ticker(120.00), "manual_button"))
        assert bot.placed, "the rig places no order at all"
