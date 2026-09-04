"""Manual Fire and the Ammo readout must agree at the dust-band edge.

``manual_fire_will_noop`` answers True when ``abs(delta)`` equals
``manual_fire_dust_band``. ``_execute_manual_rebalance`` must place no order
on that same position.
"""

from __future__ import annotations

import asyncio
from typing import Any

from src.trading.scrumming_bot import ScrummingBot
from src.trading.target_bands import manual_fire_dust_band, manual_fire_will_noop

PRICE = 1.0
TARGET = 100.0
EDGE_HOLDINGS = 101.0
PAST_EDGE_HOLDINGS = 102.0


class _Bus:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def emit(self, topic: str, **payload: Any) -> None:
        self.messages.append(f"{topic}|{payload.get('message', '')}")


class _Stats:
    def __init__(self) -> None:
        self.total_trades = 0
        self.total_scrummed_usd = 0.0
        self.trade_volume = 0.0
        self.last_trade_time = 0.0


class _Config:
    symbol = "CHIP/USD"
    target_asset = "CHIP"
    exchange_id = "coinbase"
    scrumming_interval_pct = 1.0
    trading_fee_pct = 0.6
    max_target_growth_pct = 0.0
    profit_folding_active = True
    scrum_fold_pct = 100


class _Order:
    id = "order-1"
    filled = 0.0
    average = 0.0


class _Ticker:
    def __init__(self, last: float) -> None:
        self.last = last


def _bot(holdings: float) -> Any:
    """A bot that runs the real ``_execute_manual_rebalance`` sell branch."""
    bot: Any = object.__new__(ScrummingBot)
    bot.bot_id = "edge-bot"
    bot.placed = []
    bot._bus = _Bus()
    bot.config = _Config()
    bot.stats = _Stats()
    bot._fold_tranches = []
    bot._main_lots = [{"units": holdings, "initial_buy_price": 0.9}]
    bot._current_holdings = holdings
    bot._target_balance = TARGET
    bot._anchor_target_balance = TARGET
    bot._quote_to_usd = 1.0
    bot._manual_fire_pending = True
    bot._tranches_created_lifetime = 0
    bot._fold_queue_usd = 0.0
    bot._last_trade_side = None
    bot._last_trade_price = 0.0
    bot._last_bb = None
    bot._pending_wire_credits = 0.0

    async def _refresh() -> float:
        return 1.0

    async def _place(**kwargs: Any) -> _Order:
        bot.placed.append(dict(kwargs))
        return _Order()

    async def _settled(
        order: Any, symbol: str, requested: float, tick_price: float
    ) -> tuple[float, float, bool]:
        del order, symbol, tick_price
        return requested, PRICE, True

    async def _balance(currency: str) -> Any:
        del currency
        return type("B", (), {"total": holdings, "free": holdings, "absent": False})()

    def _ignore(*args: Any, **kwargs: Any) -> None:
        del args, kwargs

    def _route(scrum_usd: float, sell_fill: float, label: str) -> float:
        del scrum_usd, sell_fill, label
        return 0.0

    bot._refresh_quote_to_usd = _refresh
    bot.guarded_place_order = _place
    bot._settled_fill = _settled
    bot._get_balance = _balance
    bot._route_scrum_proceeds_via_wires = _route
    bot._emit_voting_panel_snapshot_at_fire = _ignore
    bot._emit_gate_decision_at_fire = _ignore
    bot._reset_opposing_hysteresis_after_fill = _ignore
    bot.note_scrum_retention_usd = _ignore
    return bot


def _fire(holdings: float) -> Any:
    bot = _bot(holdings)
    asyncio.run(bot._execute_manual_rebalance(_Ticker(PRICE), "manual_button"))
    return bot


def test_the_edge_position_sits_exactly_on_the_band() -> None:
    """The scenario is honest only if the delta equals the band exactly."""
    delta = EDGE_HOLDINGS * PRICE - TARGET
    band = manual_fire_dust_band(TARGET)
    assert delta == band, (
        f"delta {delta!r} is not the band {band!r}; the edge case below "
        f"would prove nothing"
    )


def test_the_readout_calls_the_edge_position_a_no_op() -> None:
    """``manual_fire_will_noop`` answers True on the edge and False past it."""
    assert manual_fire_will_noop(EDGE_HOLDINGS * PRICE, TARGET) is True
    assert manual_fire_will_noop(PAST_EDGE_HOLDINGS * PRICE, TARGET) is False


def test_manual_fire_places_no_order_at_the_band_edge() -> None:
    """The engine refuses where the readout says it will."""
    bot = _fire(EDGE_HOLDINGS)
    assert bot.placed == [], (
        f"Manual Fire traded at the band edge while the readout predicted a "
        f"no-op; orders placed: {bot.placed}"
    )
    assert any(
        "dust band" in m for m in bot._bus.messages
    ), f"no dust-band no-op was logged: {bot._bus.messages}"


def test_manual_fire_sells_past_the_band_edge() -> None:
    """The control: the same rig sees an order when one is placed."""
    bot = _fire(PAST_EDGE_HOLDINGS)
    assert len(bot.placed) == 1, f"expected one order, saw {bot.placed}"
    assert bot.placed[0]["side"].value == "sell"
