"""Nuclear must not fill a limit order at a price the market never saw.

Found during the C19 cold read. NOT in the cascade plan, and more severe
than any finding it lists.

THE DEFECT
`nuclear_sim_exchange.py:244-245`:

    fill_price = float(c[4])                       # candle close
    if order_type == OrderType.LIMIT and price is not None:
        fill_price = float(price)                  # whatever was named

No crosses test. No comparison against the candle at all. A BUY limit at
$1.00 against a $100 candle fills at $1.00.

That is not "an unrealistic resting model" — it is free money. Any
strategy evaluated in Nuclear that places limit orders has been scored
against a fabricated discount, and the further from market it bids the
better it appears to do. A backtest that rewards bidding absurdly low is
worse than no backtest: it actively recommends the wrong behaviour.

WHY THIS SHIPS ALONE
Operator decision 2026-08-07. It is a handful of lines, it invalidates
any Nuclear result involving limit orders, and isolating it keeps the
decision diff readable before the four other C19 findings land.

THE CONTRACT BEING ESTABLISHED
A limit order fills only if the candle actually traded through the limit
price, and then at a price the market could have given:

  BUY  fills iff candle_low  <= limit ; at min(limit, close)
  SELL fills iff candle_high >= limit ; at max(limit, close)

`min`/`max` rather than the limit itself: a BUY limit ABOVE the market
must not fill at the (worse) limit price when the market was cheaper —
that would be a fabricated LOSS, the mirror of the defect being fixed.

Fleet's model is deliberately NOT copied here. Fleet rests the order and
sweeps it later; Nuclear is single-shot by design. This pins the FILL
PRICE, not the resting semantics — the venues stay forks.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.exchange.base import OrderSide, OrderType  # noqa: E402
from src.simulator.nuclear_sim_exchange import (  # noqa: E402
    NuclearSimExchange,
)

SYM = "BTC/USD"
# open, high, low, close — a candle that traded 95..105 and closed 100.
CANDLE = [0, 100.0, 105.0, 95.0, 100.0, 10.0]


class _Src:
    """Minimal candle source: one tape, one current candle."""

    def __init__(self, candle=None):
        self._c = list(candle if candle is not None else CANDLE)

    def current(self, _tape_id):
        return list(self._c)

    def set(self, candle):
        self._c = list(candle)


def _venue(candle=None):
    ex = object.__new__(NuclearSimExchange)
    ex._src = _Src(candle)
    ex._fee_pct = 0.0
    ex._balances = {"USD": 1_000_000.0, "BTC": 1_000.0}
    ex._exchange_id = "nuclear_sim"
    ex._connected = True
    ex._trades = []
    ex._orders = {}
    ex._resolve_tape = lambda _sym: "tape"
    return ex


async def _place(ex, side, otype, amount, price=None):
    return await ex.place_order(
        symbol=SYM, side=side, order_type=otype, amount=amount, price=price
    )


class TestTheInstrumentWorks:
    @pytest.mark.asyncio
    async def test_a_market_order_fills_at_the_close(self):
        """POSITIVE CONTROL. Every assertion below compares against the
        close; if market orders stopped filling there, they would all be
        measuring the wrong baseline."""
        o = await _place(_venue(), OrderSide.BUY, OrderType.MARKET, 1.0)
        assert o.average == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_the_candle_actually_spans_the_test_prices(self):
        """The fixture's premise: 95..105 brackets the close, so
        'inside the range' and 'outside it' are both expressible."""
        c = _Src().current("t")
        assert c[3] < c[4] < c[2]


class TestFreeMoneyIsGone:
    @pytest.mark.asyncio
    async def test_a_buy_far_below_the_market_does_not_fill_at_its_limit(self):
        """THE defect. A $1.00 bid against a $100 market filled at $1.00
        — a 99% fabricated discount, and better the lower it bid."""
        o = await _place(_venue(), OrderSide.BUY, OrderType.LIMIT, 1.0, price=1.0)
        assert o.average != pytest.approx(1.0), (
            "a BUY limit filled at a price the market never traded; "
            "any strategy bidding low is being paid to do so"
        )

    @pytest.mark.asyncio
    async def test_a_sell_far_above_the_market_does_not_fill_at_its_limit(self):
        """The mirror: asking $10,000 into a $100 market."""
        o = await _place(_venue(), OrderSide.SELL, OrderType.LIMIT, 1.0, price=10_000.0)
        assert o.average != pytest.approx(10_000.0)

    @pytest.mark.asyncio
    async def test_an_unfillable_buy_does_not_report_a_fill(self):
        """Not filling is the honest outcome — reporting a fill at the
        close would be a different fabrication."""
        o = await _place(_venue(), OrderSide.BUY, OrderType.LIMIT, 1.0, price=1.0)
        assert float(getattr(o, "filled", 0) or 0) == 0.0

    @pytest.mark.asyncio
    async def test_an_unfillable_order_moves_no_balance(self):
        """The ledger must not record a purchase that did not happen."""
        ex = _venue()
        before = dict(ex._balances)
        await _place(ex, OrderSide.BUY, OrderType.LIMIT, 1.0, price=1.0)
        assert ex._balances == before


class TestFillableLimitsStillFill:
    @pytest.mark.asyncio
    async def test_a_buy_at_or_above_the_low_fills(self):
        """NEGATIVE CONTROL: refusing everything would 'fix' the defect
        while removing limit orders from the simulator entirely."""
        o = await _place(_venue(), OrderSide.BUY, OrderType.LIMIT, 1.0, price=98.0)
        assert float(getattr(o, "filled", 0) or 0) > 0.0

    @pytest.mark.asyncio
    async def test_a_sell_at_or_below_the_high_fills(self):
        o = await _place(_venue(), OrderSide.SELL, OrderType.LIMIT, 1.0, price=102.0)
        assert float(getattr(o, "filled", 0) or 0) > 0.0

    @pytest.mark.asyncio
    async def test_a_buy_above_the_market_fills_at_the_market_not_the_limit(self):
        """The mirror of the defect: a BUY limit ABOVE the market must
        not fill at its own (worse) price when the market was cheaper.
        That would fabricate a LOSS."""
        o = await _place(_venue(), OrderSide.BUY, OrderType.LIMIT, 1.0, price=104.0)
        assert o.average == pytest.approx(
            100.0
        ), f"filled at {o.average}, worse than the {100.0} close"

    @pytest.mark.asyncio
    async def test_a_sell_below_the_market_fills_at_the_market(self):
        o = await _place(_venue(), OrderSide.SELL, OrderType.LIMIT, 1.0, price=96.0)
        assert o.average == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_a_marketable_buy_never_fills_above_its_limit(self):
        """The limit is a ceiling for a BUY, whatever the close does."""
        ex = _venue([0, 100.0, 105.0, 95.0, 103.0, 10.0])  # close 103
        o = await _place(ex, OrderSide.BUY, OrderType.LIMIT, 1.0, price=99.0)
        if float(getattr(o, "filled", 0) or 0) > 0.0:
            assert o.average <= 99.0 + 1e-9


class TestAnUnfundedOrderIsRefused:
    @pytest.mark.asyncio
    async def test_a_buy_with_no_quote_currency_raises(self):
        """`_adjust_balance` has no floor, so without the precondition a
        BUY settles and drives the ledger negative."""
        ex = _venue()
        ex._balances = {"USD": 0.0, "BTC": 0.0}
        with pytest.raises(ValueError):
            await _place(ex, OrderSide.BUY, OrderType.MARKET, 1.0)
        assert ex._balances["USD"] == 0.0, "a refused order still moved the ledger"

    @pytest.mark.asyncio
    async def test_a_sell_of_coins_never_held_raises(self):
        """The SELL half of the same precondition: the venue checks the
        base balance, not only the quote."""
        ex = _venue()
        ex._balances = {"USD": 1_000.0, "BTC": 0.0}
        with pytest.raises(ValueError):
            await _place(ex, OrderSide.SELL, OrderType.MARKET, 1.0)
        assert ex._balances["BTC"] == 0.0, "a refused order still moved the ledger"

    @pytest.mark.asyncio
    async def test_the_same_sell_settles_when_the_coins_are_there(self):
        """POSITIVE CONTROL for the two refusals above: a venue that
        refused every order would pass them while trading nothing."""
        ex = _venue()
        ex._balances = {"USD": 1_000.0, "BTC": 1.0}
        o = await _place(ex, OrderSide.SELL, OrderType.MARKET, 1.0)
        assert float(getattr(o, "filled", 0) or 0) == pytest.approx(1.0)
        assert ex._balances["BTC"] == pytest.approx(0.0)
