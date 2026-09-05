"""Manual Fire books the fill the venue settled, never the size it asked for.

``CCXTConnector._parse_order`` carries ``average`` off the payload, and
``ScrummingBot._settled_fill`` re-reads a placed order until the venue reports
a real amount and price. ``fire_manual`` drives ``_execute_manual_rebalance``
on both branches with an ``_EmptyOrder`` carrying no numeric field. Every
amount booked in ``TestTheCallSitesUseIt`` comes from ``_RefetchExchange``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.exchange.ccxt_connector import CCXTConnector  # noqa: E402
from src.trading.scrumming_bot import ScrummingBot  # noqa: E402


# The root cause: _parse_order must carry `average`
class TestParseOrderCarriesTheFillPrice:
    def test_average_is_populated_from_the_payload(self):
        """POSITIVE CONTROL. Everything downstream reads this field."""
        o = CCXTConnector._parse_order(
            {
                "id": "x",
                "symbol": "BTC/USD",
                "side": "buy",
                "type": "market",
                "amount": 1.0,
                "filled": 1.0,
                "average": 250.0,
                "status": "closed",
            }
        )
        assert o.average == pytest.approx(250.0)

    def test_it_falls_back_to_cost_over_filled(self):
        """Some venues omit `average` and report `cost` (= filled x avg)."""
        o = CCXTConnector._parse_order(
            {
                "id": "x",
                "symbol": "BTC/USD",
                "side": "buy",
                "type": "market",
                "filled": 4.0,
                "cost": 1000.0,
                "status": "closed",
            }
        )
        assert o.average == pytest.approx(250.0)

    def test_an_unfilled_order_reports_zero_not_a_divide_by_zero(self):
        o = CCXTConnector._parse_order(
            {
                "id": "x",
                "symbol": "BTC/USD",
                "side": "buy",
                "type": "market",
                "filled": 0.0,
                "cost": 0.0,
                "status": "open",
            }
        )
        assert o.average == 0.0

    def test_the_coinbase_create_order_payload_still_parses(self):
        """NEGATIVE CONTROL: the real create_order response carries none
        of these fields. It must yield zeros, not raise."""
        o = CCXTConnector._parse_order(
            {
                "id": "abc",
                "symbol": "BTC/USD",
                "side": "buy",
            }
        )
        assert o.average == 0.0 and o.filled == 0.0


# _settled_fill
class _Order:
    def __init__(self, oid="oid-1", filled=0.0, average=0.0):
        self.id = oid
        self.filled = filled
        self.average = average


class _Exchange:
    """Returns a sequence of orders from get_order, one per call."""

    def __init__(self, *sequence):
        self._seq = list(sequence)
        self.calls = 0

    async def get_order(self, order_id, symbol):
        del order_id, symbol
        self.calls += 1
        if not self._seq:
            return None
        return self._seq.pop(0) if len(self._seq) > 1 else self._seq[0]


class _Boom:
    def __init__(self):
        self.calls = 0

    async def get_order(self, order_id, symbol):
        del order_id, symbol
        self.calls += 1
        raise RuntimeError("exchange unreachable")


def _bot(exchange=None):
    b = object.__new__(ScrummingBot)
    b.bot_id = "b1"
    b.exchange = exchange
    b._bus = type("B", (), {"emit": lambda self, *_a, **_k: None})()
    return b


class TestItPrefersWhatTheExchangeReports:
    @pytest.mark.asyncio
    async def test_a_complete_order_is_used_without_refetching(self):
        """POSITIVE CONTROL, and the no-extra-API-call guarantee."""
        ex = _Exchange()
        amt, px, real = await _bot(ex)._settled_fill(
            _Order(filled=2.0, average=50.0), "BTC/USD", 9.0, 99.0
        )
        assert (amt, px, real) == (pytest.approx(2.0), pytest.approx(50.0), True)
        assert ex.calls == 0

    @pytest.mark.asyncio
    async def test_an_empty_order_is_refetched(self):
        """The Coinbase case: create_order says nothing, fetch_order does."""
        ex = _Exchange(_Order(filled=3.0, average=20.0))
        amt, px, real = await _bot(ex)._settled_fill(_Order(), "BTC/USD", 9.0, 99.0)
        assert (amt, px, real) == (pytest.approx(3.0), pytest.approx(20.0), True)
        assert ex.calls >= 1

    @pytest.mark.asyncio
    async def test_it_polls_until_the_order_settles(self):
        """A market order is not settled the instant create_order returns."""
        ex = _Exchange(_Order(), _Order(filled=1.5, average=30.0))
        amt, px, real = await _bot(ex)._settled_fill(_Order(), "BTC/USD", 9.0, 99.0)
        assert real is True and amt == pytest.approx(1.5)
        assert ex.calls >= 2


class TestFallingBackIsAllowedButNeverSilent:
    @pytest.mark.asyncio
    async def test_it_estimates_when_the_exchange_never_reports(self):
        """The order DID execute. Refusing to book it would be worse
        than booking an estimate -- but it must be flagged."""
        amt, px, real = await _bot(_Exchange(_Order()))._settled_fill(
            _Order(), "BTC/USD", 9.0, 99.0
        )
        assert (amt, px) == (pytest.approx(9.0), pytest.approx(99.0))
        assert real is False, "an estimate must not be reported as a real fill"

    @pytest.mark.asyncio
    async def test_the_operator_is_told(self):
        emitted = []
        b = _bot(_Exchange(_Order()))
        b._bus = type(
            "B",
            (),
            {"emit": lambda self, *_a, **_k: emitted.append(_k.get("message", ""))},
        )()
        await b._settled_fill(_Order(), "BTC/USD", 9.0, 99.0)
        assert any(
            "ESTIMATE" in m for m in emitted
        ), "a fabricated fill must say so in the log"

    @pytest.mark.asyncio
    async def test_a_raising_exchange_does_not_propagate(self):
        """This runs after the order is already placed. Raising here
        would abandon the accounting for a trade that really happened."""
        ex = _Boom()
        amt, px, real = await _bot(ex)._settled_fill(_Order(), "BTC/USD", 9.0, 99.0)
        assert (amt, px, real) == (pytest.approx(9.0), pytest.approx(99.0), False)

    @pytest.mark.asyncio
    async def test_partial_knowledge_is_kept_not_discarded(self):
        """Amount reported, price not: keep the real amount and estimate
        only the missing half."""
        ex = _Exchange(_Order(filled=2.5, average=0.0))
        amt, px, real = await _bot(ex)._settled_fill(_Order(), "BTC/USD", 9.0, 99.0)
        assert amt == pytest.approx(2.5), "a REAL filled amount was discarded"
        assert px == pytest.approx(99.0)
        assert real is False

    @pytest.mark.asyncio
    async def test_an_order_with_no_id_skips_the_refetch(self):
        ex = _Exchange(_Order(filled=5.0, average=5.0))
        amt, px, real = await _bot(ex)._settled_fill(
            _Order(oid=""), "BTC/USD", 9.0, 99.0
        )
        assert ex.calls == 0 and real is False and amt == pytest.approx(9.0)


TICK_PRICE = 1.0
TARGET_USD = 100.0
VENUE_AMOUNT = 17.5
VENUE_PRICE = 1.25


class _VenueOrder:
    """What the venue reports on the re-read: a real amount and a real price."""

    id = "venue-1"
    filled = VENUE_AMOUNT
    average = VENUE_PRICE


class _EmptyOrder:
    """What Coinbase's create_order returns: an id and no numeric field."""

    id = "venue-1"


class _RefetchExchange:
    """Answers ``get_order`` with a settled ``_VenueOrder`` and counts calls."""

    def __init__(self):
        self.calls = 0

    async def get_order(self, order_id, symbol):
        del order_id, symbol
        self.calls += 1
        return _VenueOrder()


class _FireBus:
    """Keeps every emitted message, and every ``trade.filled`` payload."""

    def __init__(self):
        self.messages = []
        self.events = []

    def emit(self, topic, **payload):
        self.messages.append(f"{topic}|{payload.get('message', '')}")
        self.events.append((topic, payload.get("data")))

    def filled(self):
        return [data for topic, data in self.events if topic == "trade.filled"]


STALE_POSITION_VALUE = 500.0


class _FireStats:
    """``position_value`` holds a figure no live position matches."""

    def __init__(self):
        self.position_value = STALE_POSITION_VALUE
        self.total_trades = 0
        self.total_scrummed_usd = 0.0
        self.total_folded_usd = 0.0
        self.trade_volume = 0.0
        self.last_trade_time = 0.0


class _FireConfig:
    symbol = "CHIP/USD"
    target_asset = "CHIP"
    exchange_id = "coinbase"
    scrumming_interval_pct = 1.0
    trading_fee_pct = 0.6
    max_target_growth_pct = 0.0
    profit_folding_active = True
    scrum_fold_pct = 100


class _FireTicker:
    last = TICK_PRICE


def fire_manual(holdings, *, settled_fill=None, exchange=None):
    """One real ``_execute_manual_rebalance`` at $1, driven to a fill.

    ``holdings`` above ``TARGET_USD`` takes the SCRUM branch and below it the
    FOLD branch; the placed ``_EmptyOrder`` carries no numeric field, so the
    real ``_settled_fill`` re-reads it from ``exchange``.
    """
    import asyncio

    bot: Any = object.__new__(ScrummingBot)
    bot.bot_id = "settled-bot"
    bot.placed = []
    bot.exchange = _RefetchExchange() if exchange is None else exchange
    bot._bus = _FireBus()
    bot.config = _FireConfig()
    bot.stats = _FireStats()
    bot._fold_tranches = []
    bot._main_lots = [{"units": holdings, "initial_buy_price": 0.9}]
    bot._current_holdings = holdings
    bot._target_balance = TARGET_USD
    bot._anchor_target_balance = TARGET_USD
    bot._quote_to_usd = 1.0
    bot._manual_fire_pending = True
    bot._tranches_created_lifetime = 0
    bot._tranches_closed_lifetime = 0
    bot._tranches_malformed_dropped = 0
    bot._fold_queue_usd = 0.0
    bot._fold_cycle_cap_consumed = 0.0
    bot._fold_accumulator = 0.0
    bot._standing_surplus_usd = 0.0
    bot._retained_this_cycle_usd = 0.0
    bot._target_grow_last_side = None
    bot._last_trade_side = None
    bot._last_trade_price = 0.0
    bot._last_bb = None
    bot._pending_wire_credits = 0.0
    bot._last_sell_venue_fee = None

    async def _refresh():
        return 1.0

    async def _place(**kwargs):
        bot.placed.append(dict(kwargs))
        return _EmptyOrder()

    async def _balance(currency):
        free = holdings if currency == "CHIP" else 1_000_000.0
        return type("B", (), {"total": free, "free": free, "absent": False})()

    def _ignore(*args, **kwargs):
        del args, kwargs

    def _zero(*args, **kwargs):
        del args, kwargs
        return 0.0

    bot._refresh_quote_to_usd = _refresh
    bot.guarded_place_order = _place
    bot._get_balance = _balance
    bot._record_venue_fee = _ignore
    bot._emit_voting_panel_snapshot_at_fire = _ignore
    bot._emit_gate_decision_at_fire = _ignore
    bot._reset_opposing_hysteresis_after_fill = _ignore
    bot._route_scrum_proceeds_via_wires = _zero
    bot.note_scrum_retention_usd = _ignore
    if settled_fill is not None:
        bot._settled_fill = settled_fill
    asyncio.run(bot._execute_manual_rebalance(_FireTicker(), "manual_button"))
    return bot


class TestTheCallSitesUseIt:
    """A helper nothing calls fixes nothing."""

    def test_the_scrum_branch_books_what_the_venue_reported(self):
        """The placed order carries no numbers, so the booked amount and
        price can only have come from the re-read."""
        bot = fire_manual(120.0)
        assert len(bot.placed) == 1 and bot.placed[0]["side"].value == "sell"
        assert bot.placed[0]["amount"] == pytest.approx(20.0)
        assert bot.exchange.calls >= 1, "the venue was never re-read"
        booked = bot._bus.filled()
        assert len(booked) == 1, booked
        assert booked[0]["amount"] == pytest.approx(VENUE_AMOUNT), (
            f"the SCRUM branch booked {booked[0]['amount']}, not the "
            f"{VENUE_AMOUNT} the venue reported"
        )
        assert booked[0]["price"] == pytest.approx(VENUE_PRICE)

    def test_the_fold_branch_books_what_the_venue_reported(self):
        """The buy side reads the same re-read the sell side does."""
        bot = fire_manual(80.0)
        assert len(bot.placed) == 1 and bot.placed[0]["side"].value == "buy"
        assert bot.placed[0]["amount"] == pytest.approx(20.0)
        assert bot.exchange.calls >= 1, "the venue was never re-read"
        booked = bot._bus.filled()
        assert len(booked) == 1, booked
        assert booked[0]["amount"] == pytest.approx(VENUE_AMOUNT), (
            f"the FOLD branch booked {booked[0]['amount']}, not the "
            f"{VENUE_AMOUNT} the venue reported"
        )
        assert booked[0]["price"] == pytest.approx(VENUE_PRICE)

    def test_the_scrum_branch_moves_holdings_by_the_settled_amount(self):
        """A fabricated fill would move holdings by the requested 20.0."""
        bot = fire_manual(120.0)
        assert bot._current_holdings == pytest.approx(120.0 - VENUE_AMOUNT)

    def test_the_fold_branch_moves_holdings_by_the_settled_amount(self):
        """The same drift, on the buy side."""
        bot = fire_manual(80.0)
        assert bot._current_holdings == pytest.approx(80.0 + VENUE_AMOUNT)

    @pytest.mark.parametrize("holdings", [120.0, 80.0])
    def test_neither_branch_labels_the_settled_fill(self, holdings):
        """``_settled_fill`` writes MANUAL FIRE into the operator's fallback
        line while no call site passes ``label``."""
        seen = []

        async def _spy(order, symbol, requested, quoted, *args, **kwargs):
            seen.append((args, kwargs))
            del order, symbol, quoted
            return requested, TICK_PRICE, True

        fire_manual(holdings, settled_fill=_spy)
        assert len(seen) == 1, seen
        assert seen[0] == ((), {}), f"a label reached the settled fill: {seen[0]}"
