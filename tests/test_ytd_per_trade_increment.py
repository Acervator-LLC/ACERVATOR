"""Per-trade YTD increment integration tests.

Drives the real ``_execute_sell`` / ``_execute_buy`` on minimal stub bots
and asserts that ``stats.ytd_scrummed_usd`` / ``stats.ytd_folded_usd``
accumulate the USD value of every fill (``amount × fill × _quote_to_usd``),
apply the quote→USD conversion on crypto-quoted pairs, and never let a
malformed value break the fill path.

Regression coverage for the defect where these fields only updated during
the throttled boot sync, never per trade.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.trading.scrumming_bot import ScrummingBot  # noqa: E402


class _Bus:
    def __init__(self):
        self.messages = []

    def emit(self, event, **kwargs):
        self.messages.append((event, kwargs))


class _Config:
    def __init__(self, **overrides):
        self.symbol = "ETH/USD"
        self.target_asset = "ETH"
        self.scrumming_interval_pct = 1.0
        self.trading_fee_pct = 0.6
        self.stack_mode = False
        self.position_ceiling_enabled = False
        self.max_target_growth_pct = 1.0
        for k, v in overrides.items():
            setattr(self, k, v)


class _Stats:
    def __init__(self):
        self.verify_samples = 0
        self.verify_clean = 0
        self.verify_adjusted = 0
        self.verify_canceled = 0
        self.total_sells = 0
        self.total_buys = 0
        self.total_trades = 0
        self.trade_volume = 0.0
        self.last_trade_time = 0.0


class _Exchange:
    """Nothing is ever open. Records what it was asked about, because a
    stub that discards its arguments cannot be asserted against."""

    def __init__(self):
        self.open_order_queries = []

    async def get_open_orders(self, symbol):
        self.open_order_queries.append(symbol)
        return []


class _Order:
    def __init__(self, average):
        self.id = "stub-order"
        self.average = average
        self.price = average


class _MemTrade:
    pass


class _Summary:
    consensus_direction = "sell"
    consensus_confidence = 0.75


class _TradeStubBot:
    """Minimum surface to run the real ``_execute_sell`` / ``_execute_buy``
    to completion, with every gate set permissive. NOT a ScrummingBot.

    ``market_fill`` is the price the stubbed exchange fills at, so the
    USD math is deterministic regardless of the tick price handed in.
    """

    def __init__(self, *, quote_to_usd=1.0, market_fill=100.0, holdings=1000.0):
        self.bot_id = "ytd-stub"
        self.config = _Config()
        self.stats = _Stats()
        self._bus = _Bus()
        self.exchange = _Exchange()
        self._quote_to_usd = quote_to_usd
        self._market_fill = market_fill
        self._current_holdings = holdings
        self._target_balance = 100000.0
        self._anchor_target_balance = 100000.0
        self._fold_tranches = []
        self._main_lots = []
        self._initialised = True
        self._invisible = True
        self._hyst_armed_scrum_side = False
        self._hyst_ref_scrum_side = 0.0
        self._hyst_armed_fold_side = False
        self._hyst_ref_fold_side = 0.0
        self._memorised_trades = []
        self.placed_orders = []
        self.notifications = []
        self.reconciles = []
        self.stack_spawns = []
        self.wire_routings = []
        self.retentions = []
        # issue #133 unit 9b -- the venue's fee for the last settled
        # sell. `_execute_sell` clears it and writes it.
        self._last_sell_venue_fee = None

    def _crr(self):
        return None

    def _emit_trade_notification(self, kind, state, detail):
        self.notifications.append((kind, state, detail))

    def _record_venue_fee(self, order, units, price):
        """Delegate to the REAL ScrummingBot._record_venue_fee.

        issue #133 unit 9b. ``_execute_sell`` records the venue's fee
        off the settled order. A no-op here would let this stub drift
        from the collaborator it doubles.
        """
        return ScrummingBot._record_venue_fee(self, order, units, price)

    async def _verify_buy_safe_or_refuse(self, path=""):
        return 0.0, None

    async def _reconcile_holdings(self, reason=""):
        self.reconciles.append(reason)
        return None

    async def _spawn_stack_from_fold(self, fold_price, fold_size, summary, path):
        self.stack_spawns.append((fold_price, fold_size, summary, path))
        return None

    def _route_scrum_proceeds_via_wires(self, scrum_usd, sell_fill, label):
        """Routes nothing. Records the sale it was offered, so a test
        can tell "no wire took a cut" from "the call never happened"."""
        self.wire_routings.append((scrum_usd, sell_fill, label))
        return 0.0

    def note_scrum_retention_usd(self, retained_usd):
        self.retentions.append(retained_usd)

    async def guarded_place_order(self, symbol, side, order_type, amount, price):
        fill = float(price) if price else self._market_fill
        self.placed_orders.append(
            {
                "symbol": symbol,
                "side": side,
                "type": order_type,
                "amount": amount,
                "price": price,
                "fill": fill,
            }
        )
        return _Order(fill)

    def log(self):
        return [kw.get("message", "") for _, kw in self._bus.messages]


def _sell(bot, amount, price):
    return asyncio.run(
        ScrummingBot._execute_sell(
            bot, amount=amount, price=price, summary=_Summary(), bypass_stack=True
        )
    )


def _buy(bot, cost, price):
    return asyncio.run(
        ScrummingBot._execute_buy(
            bot,
            cost=cost,
            price=price,
            summary=_Summary(),
            trace_context={"path": "fold_rebuy"},
        )
    )


def _placed(bot):
    assert bot.placed_orders, "the stub never reached order placement: " + "; ".join(
        bot.log()
    )
    return bot.placed_orders[-1]


# ── the increment happens on every trade ─────────────────────────────


def test_a_sell_increments_ytd_scrummed_by_the_fill_usd():
    bot = _TradeStubBot(quote_to_usd=1.0, market_fill=100.0)
    fill = _sell(bot, amount=2.0, price=100.0)
    assert fill is not None
    order = _placed(bot)
    expected = order["amount"] * order["fill"] * 1.0
    assert bot.stats.ytd_scrummed_usd == pytest.approx(expected)
    assert expected > 0


def test_a_buy_increments_ytd_folded_by_the_fill_usd():
    bot = _TradeStubBot(quote_to_usd=1.0, market_fill=100.0)
    fill = _buy(bot, cost=200.0, price=100.0)
    assert fill is not None
    order = _placed(bot)
    expected = order["amount"] * order["fill"] * 1.0
    assert bot.stats.ytd_folded_usd == pytest.approx(expected)
    assert expected > 0


# ── the quote→USD conversion is applied on crypto-quoted pairs ───────


def test_the_sell_increment_applies_the_quote_to_usd_conversion():
    """A BTC-quoted bot must accumulate USD, not raw quote notional."""
    bot = _TradeStubBot(quote_to_usd=50.0, market_fill=100.0)
    _sell(bot, amount=2.0, price=100.0)
    order = _placed(bot)
    raw_quote_notional = order["amount"] * order["fill"]
    assert bot.stats.ytd_scrummed_usd == pytest.approx(raw_quote_notional * 50.0)
    assert bot.stats.ytd_scrummed_usd != pytest.approx(raw_quote_notional)


def test_the_buy_increment_applies_the_quote_to_usd_conversion():
    bot = _TradeStubBot(quote_to_usd=50.0, market_fill=100.0)
    _buy(bot, cost=200.0, price=100.0)
    order = _placed(bot)
    raw_quote_notional = order["amount"] * order["fill"]
    assert bot.stats.ytd_folded_usd == pytest.approx(raw_quote_notional * 50.0)
    assert bot.stats.ytd_folded_usd != pytest.approx(raw_quote_notional)


# ── a malformed value must not break the fill path ──────────────────


def test_a_malformed_prior_scrummed_total_does_not_break_the_sell():
    bot = _TradeStubBot()
    bot.stats.ytd_scrummed_usd = "corrupt"
    fill = _sell(bot, amount=2.0, price=100.0)
    assert fill is not None, "the sell was broken by a malformed ytd value"
    assert bot.stats.total_sells == 1
    assert not any("SELL FAILED" in m for m in bot.log())


def test_a_malformed_prior_folded_total_does_not_break_the_buy():
    bot = _TradeStubBot()
    bot.stats.ytd_folded_usd = "corrupt"
    fill = _buy(bot, cost=200.0, price=100.0)
    assert fill is not None, "the buy was broken by a malformed ytd value"
    assert bot.stats.total_buys == 1
    assert not any("BUY ABORTED" in m or "BUY FAILED" in m for m in bot.log())


# ── the field accumulates across trades ─────────────────────────────


def test_scrummed_total_accumulates_across_repeated_sells():
    bot = _TradeStubBot(quote_to_usd=1.0, market_fill=100.0)
    _sell(bot, amount=1.0, price=100.0)
    first = bot.stats.ytd_scrummed_usd
    _sell(bot, amount=3.0, price=100.0)
    assert bot.stats.ytd_scrummed_usd == pytest.approx(first + 300.0)
