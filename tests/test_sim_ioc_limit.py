"""IOC_LIMIT must be simulable, identically, on both venues (SN-21).

C19, second pass.

THE DEFECT — AND THE TWO VENUES FAIL IN OPPOSITE DIRECTIONS
`FleetSimExchange.place_order` dispatches MARKET and LIMIT and ends in
`else: raise ValueError(... unsupported type ...)`, so an IOC_LIMIT
order aborts the run. `NuclearSimExchange` tests only
`order_type == OrderType.LIMIT`, so an IOC_LIMIT falls through to the
market branch and fills at the candle close with **the limit price
discarded entirely**.

One harness refuses to run; the other runs and reports a fill that
ignores the caller's price cap. Two venues disagreeing is worse than
both being wrong the same way, because a result that appears on one and
not the other looks like a finding.

THIS IS NOT WAITING ON STACK MODE
The cascade plan says C40a (Stack Mode, unshipped) is what depends on
IOC_LIMIT. It is already live: `_open_stack_from_scrum`
(`src/trading/scrumming_bot.py`) selects
`OrderType.IOC_LIMIT` whenever Aggressive mode is on. So a bot the
operator can enable today cannot be replayed in Fleet at all, and is
replayed wrongly in Nuclear.

THE SEMANTICS BEING ESTABLISHED
Immediate-or-Cancel: fill what is available now at the limit or better,
cancel the rest. In a candle simulator that is the LIMIT crosses test
plus one difference that defines the type — **it never rests**.

    crosses  -> fill, at the same min/max price a LIMIT would get
    no cross -> CANCELLED, not OPEN

CANCELLED rather than OPEN is the whole point. An IOC that rests is a
LIMIT, and a simulator that quietly converts one into the other tells
the operator their taker-forcing order got a maker fill.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.exchange.base import OrderSide, OrderStatus, OrderType  # noqa: E402

SYM = "BTC/USD"
CANDLE = [0, 100.0, 105.0, 95.0, 100.0, 10.0]


class _Src:
    def __init__(self, candle=None):
        self._c = list(candle or CANDLE)

    def current(self, _tape_id):
        return list(self._c)


def _nuclear(balances=None):
    from src.simulator.nuclear_sim_exchange import NuclearSimExchange

    ex = object.__new__(NuclearSimExchange)
    ex._src = _Src()
    ex._fee_pct = 0.0
    ex._balances = dict(balances or {"USD": 1_000_000.0, "BTC": 1_000.0})
    ex._exchange_id = "nuclear_sim"
    ex._connected = True
    ex._trades = []
    ex._orders = {}
    ex._resolve_tape = lambda _s: "tape"
    return ex


def _fleet(balances=None):
    from src.simulator.fleet.candle_series import CandleSeries
    from src.simulator.fleet.sim_exchange import FleetSimExchange

    return FleetSimExchange(
        series_map={SYM: CandleSeries(symbol=SYM, rows=[list(CANDLE)])},
        starting_balances=dict(balances or {"USD": 1_000_000.0, "BTC": 1_000.0}),
    )


VENUES = [("nuclear", _nuclear), ("fleet", _fleet)]


async def _place(ex, side, otype, amount, price=None):
    return await ex.place_order(
        symbol=SYM, side=side, order_type=otype, amount=amount, price=price
    )


@pytest.mark.parametrize("name,build", VENUES, ids=[v[0] for v in VENUES])
class TestTheInstrumentWorks:
    @pytest.mark.asyncio
    async def test_a_plain_limit_still_behaves(self, name, build):
        """POSITIVE CONTROL. IOC is defined by how it DIFFERS from LIMIT,
        so the LIMIT baseline has to work for the comparison to mean
        anything."""
        o = await _place(build(), OrderSide.BUY, OrderType.LIMIT, 1.0, price=98.0)
        assert float(getattr(o, "filled", 0) or 0) > 0.0


@pytest.mark.parametrize("name,build", VENUES, ids=[v[0] for v in VENUES])
class TestIOCIsSupported:
    @pytest.mark.asyncio
    async def test_it_does_not_raise(self, name, build):
        """Fleet aborted the whole run on an unsupported type, so a bot
        in Aggressive mode could not be replayed at all."""
        await _place(build(), OrderSide.BUY, OrderType.IOC_LIMIT, 1.0, price=98.0)

    @pytest.mark.asyncio
    async def test_a_crossing_ioc_fills(self, name, build):
        o = await _place(build(), OrderSide.BUY, OrderType.IOC_LIMIT, 1.0, price=98.0)
        assert float(getattr(o, "filled", 0) or 0) > 0.0

    @pytest.mark.asyncio
    async def test_it_honours_the_limit_price(self, name, build):
        """Nuclear discarded the limit and filled at the close. A price
        cap the venue ignores is worse than no cap: the operator reads a
        fill that their real order would never have taken."""
        o = await _place(build(), OrderSide.BUY, OrderType.IOC_LIMIT, 1.0, price=99.0)
        if float(getattr(o, "filled", 0) or 0) > 0.0:
            assert o.average <= 99.0 + 1e-9, (
                f"{name} filled an IOC BUY at {o.average}, above its " f"{99.0} limit"
            )


@pytest.mark.parametrize("name,build", VENUES, ids=[v[0] for v in VENUES])
class TestIOCNeverRests:
    @pytest.mark.asyncio
    async def test_an_uncrossed_ioc_is_cancelled_not_open(self, name, build):
        """THE defining difference. An IOC that rests IS a LIMIT, and a
        simulator that converts one into the other tells the operator
        their taker-forcing order got a maker fill."""
        o = await _place(build(), OrderSide.BUY, OrderType.IOC_LIMIT, 1.0, price=1.0)
        assert (
            o.status == OrderStatus.CANCELLED
        ), f"{name} left an uncrossed IOC in status {o.status}"

    @pytest.mark.asyncio
    async def test_an_uncrossed_ioc_moves_no_balance(self, name, build):
        ex = build()
        before = dict(ex._balances)
        await _place(ex, OrderSide.BUY, OrderType.IOC_LIMIT, 1.0, price=1.0)
        assert ex._balances == before

    @pytest.mark.asyncio
    async def test_an_uncrossed_limit_still_rests_where_supported(self, name, build):
        """NEGATIVE CONTROL: making IOC cancel must not make plain LIMIT
        cancel too. Fleet rests them; Nuclear is single-shot by design,
        so only Fleet is asserted here — flattening that difference is
        exactly what the no-shared-helper reasoning protects."""
        o = await _place(build(), OrderSide.BUY, OrderType.LIMIT, 1.0, price=1.0)
        assert o.status != OrderStatus.CANCELLED


class TestBothVenuesAgree:
    @pytest.mark.asyncio
    async def test_the_same_ioc_gets_the_same_outcome(self):
        """The hazard the plan names. Before this, Fleet RAISED and
        Nuclear FILLED on identical input — a result appearing on one
        venue and not the other looks like a finding."""
        for price, label in ((98.0, "crossing"), (1.0, "uncrossed")):
            outcomes = {}
            for name, build in VENUES:
                try:
                    o = await _place(
                        build(), OrderSide.BUY, OrderType.IOC_LIMIT, 1.0, price=price
                    )
                    outcomes[name] = str(o.status)
                except Exception as exc:
                    outcomes[name] = f"raised:{type(exc).__name__}"
            assert (
                len(set(outcomes.values())) == 1
            ), f"venues disagree on a {label} IOC: {outcomes}"
