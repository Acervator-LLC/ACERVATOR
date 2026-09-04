"""Role bands and cycle pairing in `TradeClassifier`.

`classify` splits buys across FOLD, UNKNOWN and HEDGE at
`FOLD_SIZE_TOLERANCE` and `HEDGE_SIZE_MULTIPLE`. `pair_cycles` reads
`MappedTrade.side`, so a buy of any role closes a cycle.
"""

from __future__ import annotations

from src.core.trade_historian import (
    FOLD_SIZE_TOLERANCE,
    HEDGE_SIZE_MULTIPLE,
    TradeClassifier,
)

SYMBOL = "BTC/USD"
FAR_APART_MS = 200_000


def _trade(idx, side, amount, price=10.0, cost=None):
    return {
        "id": f"t{idx}",
        "timestamp": idx * FAR_APART_MS,
        "side": side,
        "amount": amount,
        "price": price,
        "cost": amount * price if cost is None else cost,
        "fee": {"cost": 0.0, "currency": "USD"},
    }


def _three_unit_buys():
    """Three buys of size 1.0, which fixes the median buy size at 1.0."""
    return [_trade(i, "buy", 1.0) for i in range(3)]


def _roles(raw):
    return [t.acervator_role for t in TradeClassifier.classify(raw, SYMBOL)]


class TestTheBuySizeBands:
    def test_a_buy_at_the_fold_tolerance_is_a_fold(self):
        raw = [*_three_unit_buys(), _trade(3, "buy", FOLD_SIZE_TOLERANCE)]
        assert _roles(raw)[-1] == "FOLD", _roles(raw)

    def test_a_buy_above_the_hedge_multiple_is_a_hedge(self):
        raw = [*_three_unit_buys(), _trade(3, "buy", HEDGE_SIZE_MULTIPLE + 0.5)]
        assert _roles(raw)[-1] == "HEDGE", _roles(raw)

    def test_a_buy_between_the_two_constants_is_unknown(self):
        between = (FOLD_SIZE_TOLERANCE + HEDGE_SIZE_MULTIPLE) / 2
        raw = [*_three_unit_buys(), _trade(3, "buy", between)]
        assert _roles(raw)[-1] == "UNKNOWN", _roles(raw)

    def test_a_buy_exactly_at_the_hedge_multiple_is_unknown(self):
        raw = [*_three_unit_buys(), _trade(3, "buy", HEDGE_SIZE_MULTIPLE)]
        assert _roles(raw)[-1] == "UNKNOWN", _roles(raw)


class TestRapidFireOutranksSize:
    def test_a_large_buy_inside_the_window_reads_rapid_fire(self):
        raw = [*_three_unit_buys()]
        close_behind = dict(_trade(3, "buy", HEDGE_SIZE_MULTIPLE + 0.5))
        close_behind["timestamp"] = raw[-1]["timestamp"] + 30_000
        raw.append(close_behind)
        assert _roles(raw)[-1] == "RAPID_FIRE", _roles(raw)

    def test_the_same_large_buy_reads_hedge_once_the_window_has_passed(self):
        raw = [*_three_unit_buys(), _trade(3, "buy", HEDGE_SIZE_MULTIPLE + 0.5)]
        assert _roles(raw)[-1] == "HEDGE", _roles(raw)


class TestTheExchangeCostWins:
    def test_cost_usd_is_the_venue_cost_not_amount_times_price(self):
        raw = [*_three_unit_buys(), _trade(3, "buy", 2.0, price=10.0, cost=17.5)]
        mapped = TradeClassifier.classify(raw, SYMBOL)
        assert mapped[-1].cost_usd == 17.5, mapped[-1]

    def test_an_absent_cost_falls_back_to_amount_times_price(self):
        raw = [*_three_unit_buys()]
        no_cost = dict(_trade(3, "buy", 2.0, price=10.0))
        del no_cost["cost"]
        raw.append(no_cost)
        mapped = TradeClassifier.classify(raw, SYMBOL)
        assert mapped[-1].cost_usd == 20.0, mapped[-1]


class TestCyclePairingReadsSideNotRole:
    def _sell_then(self, closing_amount):
        raw = [*_three_unit_buys(), _trade(3, "sell", 1.0)]
        raw.append(_trade(4, "buy", closing_amount))
        return TradeClassifier.classify(raw, SYMBOL)

    def test_an_unknown_buy_closes_a_cycle(self):
        between = (FOLD_SIZE_TOLERANCE + HEDGE_SIZE_MULTIPLE) / 2
        trades = self._sell_then(between)
        assert trades[-1].acervator_role == "UNKNOWN", trades[-1]
        cycles = TradeClassifier.pair_cycles(trades)
        assert len(cycles) == 1, [c.cycle_id for c in cycles]
        assert cycles[0].fold is trades[-1]

    def test_both_legs_carry_the_same_cycle_id(self):
        trades = self._sell_then(1.0)
        cycles = TradeClassifier.pair_cycles(trades)
        assert cycles[0].scrum.cycle_id == cycles[0].fold.cycle_id == "CYC-0001"

    def test_a_run_with_no_sell_pairs_nothing(self):
        trades = TradeClassifier.classify(_three_unit_buys(), SYMBOL)
        assert TradeClassifier.pair_cycles(trades) == []
