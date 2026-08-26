"""The FOLD_DIAG counter must measure the same eligibility the executor fires on.

The autonomous fold-back and its FOLD_DIAG diagnostic both call
``ScrummingBot._fold_eligible_tranches`` — one definition of fold
eligibility, so the counter can never report a different set than the
one that fires. These tests drive that shared method on a real
ScrummingBot and pin the predicate:

    ticker.last <= ref * fold_rebuy_factor(interval, fee)

including the two regimes the original defect got wrong: a strict ``<``
that disagreed at the boundary, and an ``initial_buy_price`` term the
executor never had.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.trading.otd_math import (  # noqa: E402
    fold_rebuy_factor_from_pct,
    minimum_opposing_trade_distance_pct,
)
from src.trading.scrumming_bot import ScrummingBot  # noqa: E402


def _factor(interval=1.0, fee=0.6) -> float:
    """The OTD factor exactly as tick() derives it."""
    return fold_rebuy_factor_from_pct(
        minimum_opposing_trade_distance_pct(interval, fee)
    )


def _bot(tranches):
    bot = object.__new__(ScrummingBot)
    bot._fold_tranches = [dict(t) for t in tranches]
    return bot


def _tranche(ref, initial_buy_price=None):
    t = {"ref": ref, "units": 1.0, "usd": ref}
    if initial_buy_price is not None:
        t["initial_buy_price"] = initial_buy_price
    return t


def test_a_tranche_is_eligible_when_price_is_at_or_below_ref_times_factor():
    factor = _factor()
    ref = 1.0
    edge = ref * factor
    bot = _bot([_tranche(ref)])
    assert (
        len(bot._fold_eligible_tranches(edge, factor)) == 1
    ), "price AT the edge is eligible (<=)"
    assert (
        len(bot._fold_eligible_tranches(edge * 0.5, factor)) == 1
    ), "a deep drop is eligible"


def test_one_float_above_the_edge_is_not_eligible():
    factor = _factor()
    ref = 1.0
    edge = ref * factor
    bot = _bot([_tranche(ref)])
    above = math.nextafter(edge, math.inf)
    assert bot._fold_eligible_tranches(above, factor) == []


def test_the_boundary_is_inclusive_where_the_old_strict_less_than_excluded():
    """At exactly ref*factor the tranche IS eligible; the retired strict
    ``<`` form would have excluded it."""
    factor = _factor()
    ref = 2.0
    edge = ref * factor
    bot = _bot([_tranche(ref)])
    eligible = bot._fold_eligible_tranches(edge, factor)
    assert len(eligible) == 1
    assert eligible[0]["ref"] == ref


def test_initial_buy_price_is_not_a_gate():
    """A tranche the executor would refuse (price > ref*factor) must be
    excluded even when price <= initial_buy_price. The retired predicate
    mixed initial_buy_price in and reported it eligible."""
    factor = _factor()
    ref = 1.0
    price = math.nextafter(ref * factor, math.inf)  # just above the real edge
    # initial_buy_price well above the price: the old term would admit it
    bot = _bot([_tranche(ref, initial_buy_price=price * 10.0)])
    assert bot._fold_eligible_tranches(price, factor) == [], (
        "a tranche past its ref*factor edge was admitted on the "
        "strength of initial_buy_price — the retired gate is back"
    )


def test_the_eligible_set_is_exactly_the_predicate_over_a_ladder():
    factor = _factor()
    refs = [2.00, 1.50, 1.00, 0.50, 0.10]
    ladder = [_tranche(r) for r in refs]
    bot = _bot(ladder)
    price = 1.00
    got = {t["ref"] for t in bot._fold_eligible_tranches(price, factor)}
    expected = {r for r in refs if price <= r * factor}
    assert got == expected
    assert (
        expected
    ), "pick a price that leaves at least one eligible, or the test is vacuous"


def test_a_malformed_ref_is_never_eligible_at_a_positive_price():
    factor = _factor()
    bot = _bot([{"units": 1.0}, {"ref": 0.0}, {"ref": -1.0}])
    assert bot._fold_eligible_tranches(0.5, factor) == []


@pytest.mark.parametrize(
    "interval, fee", [(1.0, 0.6), (5.0, 1.6), (15.0, 0.6), (2.0, 0.0)]
)
def test_the_edge_tracks_otd_math_across_configs(interval, fee):
    factor = _factor(interval, fee)
    ref = 1.0
    edge = ref * factor
    bot = _bot([_tranche(ref)])
    assert len(bot._fold_eligible_tranches(edge, factor)) == 1
    assert bot._fold_eligible_tranches(math.nextafter(edge, math.inf), factor) == []
