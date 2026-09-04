"""Slippage from ``fill_price`` is adverse and does not average out.

``TestSlippageIsAlwaysAgainstTheTrader`` pins the sign of every draw and the
mean displacement ``PRICE`` * ``SPREAD`` * sqrt(2/pi) over ``N`` samples.
``TestTheInstrumentWorks`` shows ``_draws`` varies before any of that is read.
``TestZeroAndDegenerateInputs`` covers a non-positive price and a zero spread.
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.execution_discipline import fill_price  # noqa: E402

PRICE = 100.0
SPREAD = 0.001  # 0.1%
N = 20_000


def _draws(side, spread=SPREAD, seed=20260807):
    random.seed(seed)
    return [fill_price(PRICE, side, spread=spread) for _ in range(N)]


class TestTheInstrumentWorks:
    def test_the_draw_actually_varies(self):
        """Positive control: ``_draws`` returns many distinct values."""
        assert len(set(_draws("buy"))) > 100


class TestSlippageIsAlwaysAgainstTheTrader:
    def test_a_buy_never_fills_below_the_intended_price(self):
        assert min(_draws("buy")) >= PRICE - 1e-12

    def test_a_sell_never_fills_above_the_intended_price(self):
        assert max(_draws("sell")) <= PRICE + 1e-12

    def test_the_mean_cost_is_positive_not_zero(self):
        """The mean of ``_draws`` sits ``SPREAD`` * sqrt(2/pi) above ``PRICE``."""
        expected = PRICE * SPREAD * math.sqrt(2.0 / math.pi)
        buys = _draws("buy")
        mean_cost = sum(buys) / len(buys) - PRICE
        assert mean_cost > 0.0, "slippage averaged to zero or better"
        assert mean_cost == pytest.approx(expected, rel=0.10), (
            f"mean adverse slippage {mean_cost:.6f} does not match the "
            f"half-normal expectation {expected:.6f}"
        )

    def test_it_does_not_cancel_out_over_many_fills(self):
        """The summed cost of ``_draws`` grows with the sample count ``N``."""
        buys = _draws("buy")
        total_cost = sum(b - PRICE for b in buys)
        assert total_cost > 0.0
        half = _draws("buy", seed=20260807)[: N // 2]
        half_cost = sum(b - PRICE for b in half)
        assert total_cost > half_cost * 1.5


class TestZeroAndDegenerateInputs:
    @pytest.mark.parametrize("bad", [0.0, -1.0])
    def test_a_nonpositive_price_is_returned_unchanged(self, bad):
        assert fill_price(bad, "buy") == bad

    def test_a_zero_spread_produces_no_slippage(self):
        """A zero ``spread`` leaves ``PRICE`` unmoved on both sides."""
        assert fill_price(PRICE, "buy", spread=0.0) == pytest.approx(PRICE)
        assert fill_price(PRICE, "sell", spread=0.0) == pytest.approx(PRICE)
