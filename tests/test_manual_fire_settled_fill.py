"""Manual Fire must book the REAL fill, not the one it asked for (M6).

THE DEFECT
ccxt's ``coinbase.create_order`` returns only
``{success, order_id, product_id, side, client_order_id}``. Every numeric
field is absent, so ``_parse_order`` coerced them to 0 and the caller's
``or`` chains fell through to the REQUESTED size and the TICK price:

    _filled_raw = order.filled or order.amount or sell_amount
    fill_price  = order.average_price or order.average or order.price or price

The bot then booked those as if they were the fill. Holdings drift
compounds across successive fires and corrupts the NEXT delta, which is
what made the operator's amounts "strange, intermittent and hard to
explain".

THE ROOT CAUSE WAS ONE MISSING FIELD
``Order.average`` is declared on the dataclass (base.py:90) and
``_parse_order`` -- the ONLY place the connector builds an Order --
never populated it. So ``order.average`` was 0.0 on every live order
ever placed. Eleven call sites read it as the PRIMARY fill price
(scrumming_bot 2952/9334/9533/10042/10359, extractor_bot
1043/1242/1402, volume_guard 493/530/584), each with an ``or`` fallback,
so it never raised -- it just meant every live fill price was an
estimate. ``sim_exchange.py:440`` DOES set it, so the simulator had real
fill prices and live never did.
"""

from __future__ import annotations

import sys
from pathlib import Path

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
        self.calls += 1
        if not self._seq:
            return None
        return self._seq.pop(0) if len(self._seq) > 1 else self._seq[0]


class _Boom:
    def __init__(self):
        self.calls = 0

    async def get_order(self, order_id, symbol):
        self.calls += 1
        raise RuntimeError("exchange unreachable")


def _bot(exchange=None):
    b = object.__new__(ScrummingBot)
    b.bot_id = "b1"
    b.exchange = exchange
    b._bus = type("B", (), {"emit": lambda self, *a, **k: None})()
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
            {"emit": lambda self, *a, **k: emitted.append(k.get("message", ""))},
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


class TestTheCallSitesUseIt:
    """A helper nothing calls fixes nothing."""

    def test_both_manual_fire_branches_call_settled_fill(self):
        """Counted over the AST. An earlier version of this test counted
        substrings and read 3 for 2 real calls -- the third was the word
        appearing in a comment. Same trap this codebase keeps setting."""
        import ast
        import inspect

        import src.trading.scrumming_bot as m

        src = Path(
            inspect.getsourcefile(m.ScrummingBot._execute_manual_rebalance)
        ).read_text(encoding="utf-8")
        fn = next(
            n
            for n in ast.walk(ast.parse(src))
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "_execute_manual_rebalance"
        )
        calls = [
            n
            for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and getattr(n.func, "attr", "") == "_settled_fill"
        ]
        assert (
            len(calls) == 2
        ), f"SCRUM and FOLD must both read the settled fill; found {len(calls)}"

    def test_the_old_fabricating_chain_is_gone_from_manual_fire(self):
        """Asserted over the AST, not the source text: a comment
        explaining the removal names the removed thing."""
        import ast
        import inspect

        import src.trading.scrumming_bot as m

        src = Path(
            inspect.getsourcefile(m.ScrummingBot._execute_manual_rebalance)
        ).read_text(encoding="utf-8")
        fn = next(
            n
            for n in ast.walk(ast.parse(src))
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "_execute_manual_rebalance"
        )
        assigned = {
            t.id
            for n in ast.walk(fn)
            if isinstance(n, ast.Assign)
            for t in n.targets
            if isinstance(t, ast.Name)
        }
        assert "_filled_raw" not in assigned
