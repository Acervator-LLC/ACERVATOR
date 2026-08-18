"""A sim order must not settle against money that is not there (SN-17).

C19, second pass. Parameterised over BOTH venues — the plan is explicit
that they must not disagree, and two harnesses giving different answers
means neither is authoritative.

THE DEFECT
Neither venue reads a balance before debiting it. Both `_adjust_balance`
bodies are plain addition:

    self._balances[c] = self._balances.get(c, 0.0) + float(delta)

No floor, no compare, no raise. A BUY with no quote currency settles and
drives the balance negative; a SELL of coins never held settles too.

WHY IT MATTERS MORE THAN IT LOOKS
Every number downstream of a sim run is denominated in that ledger. A
replay that spends money it never had reports P&L, fill counts and
target-growth figures computed against an impossible starting position
— and reports them with no indication anything went wrong. The run does
not fail; it lies quietly.

`nuclear_sim_exchange.py` even DOCUMENTED the guarantee it did not
provide: "unknown symbols + zero balances + negative amounts all raise
loud exceptions". Corrected in v3.24.65; this cascade makes the claim
true instead.

WHY IT RAISES RATHER THAN RETURNING A REFUSAL
Both venues already raise `ValueError` for amount<=0, unknown symbol and
missing candle. An insufficient balance is the same class of caller
error, and R28 says fail loud. A silent refusal would reproduce the
defect in a new shape: the caller carries on believing it traded.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.exchange.base import OrderSide, OrderType  # noqa: E402

SYM = "BTC/USD"
CANDLE = [0, 100.0, 105.0, 95.0, 100.0, 10.0]


class _Src:
    def __init__(self, candle=None):
        self._c = list(candle or CANDLE)

    def current(self, _tape_id):
        return list(self._c)


def _nuclear(balances):
    from src.gui.simulator_tab.nuclear_sim_exchange import NuclearSimExchange

    ex = object.__new__(NuclearSimExchange)
    ex._src = _Src()
    ex._fee_pct = 0.0
    ex._balances = dict(balances)
    ex._exchange_id = "nuclear_sim"
    ex._connected = True
    ex._trades = []
    ex._orders = {}
    ex._resolve_tape = lambda _s: "tape"
    return ex


def _fleet(balances):
    from src.gui.simulator_tab.fleet.sim_exchange import FleetSimExchange
    from src.gui.simulator_tab.fleet.candle_series import CandleSeries

    series = CandleSeries(symbol=SYM, rows=[list(CANDLE)])
    ex = FleetSimExchange(series_map={SYM: series},
                          starting_balances=dict(balances))
    return ex


# Both venues, same contract. A parameterisation that silently skipped
# one would let them drift, which is the hazard the plan names.
VENUES = [("nuclear", _nuclear), ("fleet", _fleet)]


async def _place(ex, side, amount, price=None,
                 otype=OrderType.MARKET):
    return await ex.place_order(symbol=SYM, side=side, order_type=otype,
                                amount=amount, price=price)


@pytest.mark.parametrize("name,build", VENUES, ids=[v[0] for v in VENUES])
class TestTheInstrumentWorks:
    @pytest.mark.asyncio
    async def test_a_funded_order_settles(self, name, build):
        """POSITIVE CONTROL. Every refusal assertion below is only
        meaningful if a funded order still works on this venue."""
        ex = build({"USD": 1_000.0, "BTC": 10.0})
        o = await _place(ex, OrderSide.BUY, 1.0)
        assert float(getattr(o, "filled", 0) or 0) > 0.0

    @pytest.mark.asyncio
    async def test_the_venue_exposes_a_readable_ledger(self, name, build):
        ex = build({"USD": 1_000.0, "BTC": 10.0})
        assert isinstance(getattr(ex, "_balances", None), dict)


@pytest.mark.parametrize("name,build", VENUES, ids=[v[0] for v in VENUES])
class TestAnUnfundedOrderIsRefused:
    @pytest.mark.asyncio
    async def test_a_buy_with_no_quote_currency_raises(self, name, build):
        ex = build({"USD": 0.0, "BTC": 0.0})
        with pytest.raises(ValueError):
            await _place(ex, OrderSide.BUY, 1.0)

    @pytest.mark.asyncio
    async def test_a_sell_of_coins_never_held_raises(self, name, build):
        ex = build({"USD": 1_000.0, "BTC": 0.0})
        with pytest.raises(ValueError):
            await _place(ex, OrderSide.SELL, 1.0)

    @pytest.mark.asyncio
    async def test_a_buy_just_over_the_balance_raises(self, name, build):
        """The boundary, not just the empty case: 100.0 of quote buys
        1.0 at 100.0 exactly, so 1.01 must not settle."""
        ex = build({"USD": 100.0, "BTC": 0.0})
        with pytest.raises(ValueError):
            await _place(ex, OrderSide.BUY, 1.01)

    @pytest.mark.asyncio
    async def test_the_ledger_never_goes_negative(self, name, build):
        """The property the whole cascade is about, asserted directly."""
        ex = build({"USD": 50.0, "BTC": 0.0})
        try:
            await _place(ex, OrderSide.BUY, 1.0)
        except ValueError:
            pass
        assert all(v >= 0.0 for v in ex._balances.values()), (
            f"{name} ledger went negative: {ex._balances}")

    @pytest.mark.asyncio
    async def test_a_refused_order_moves_nothing(self, name, build):
        ex = build({"USD": 50.0, "BTC": 0.0})
        before = dict(ex._balances)
        with pytest.raises(ValueError):
            await _place(ex, OrderSide.BUY, 1.0)
        assert ex._balances == before


@pytest.mark.parametrize("name,build", VENUES, ids=[v[0] for v in VENUES])
class TestTheBoundaryIsNotOverTightened:
    @pytest.mark.asyncio
    async def test_spending_the_exact_balance_is_allowed(self, name, build):
        """NEGATIVE CONTROL. An off-by-one that refuses an exactly-funded
        order would quietly suppress the last trade of every run, which
        is harder to notice than the defect being fixed."""
        ex = build({"USD": 100.0, "BTC": 0.0})
        o = await _place(ex, OrderSide.BUY, 1.0)
        assert float(getattr(o, "filled", 0) or 0) > 0.0

    @pytest.mark.asyncio
    async def test_selling_the_exact_holding_is_allowed(self, name, build):
        ex = build({"USD": 0.0, "BTC": 1.0})
        o = await _place(ex, OrderSide.SELL, 1.0)
        assert float(getattr(o, "filled", 0) or 0) > 0.0


class TestBothVenuesAgree:
    @pytest.mark.asyncio
    async def test_the_same_unfunded_order_fails_the_same_way(self):
        """The hazard the plan names: two harnesses that disagree mean
        neither is authoritative. Same input, same class of failure."""
        outcomes = {}
        for name, build in VENUES:
            ex = build({"USD": 0.0, "BTC": 0.0})
            try:
                await _place(ex, OrderSide.BUY, 1.0)
                outcomes[name] = "settled"
            except ValueError:
                outcomes[name] = "refused"
        assert len(set(outcomes.values())) == 1, (
            f"the two sim venues disagree: {outcomes}")
