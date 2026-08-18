"""Slippage is adverse and does NOT average out (SN-18, closed).

`execution_discipline.fill_price` described itself as a "zero-mean
half-normal" draw. That is a contradiction. `abs()` of a zero-mean
normal is a half-normal, whose mean is `spread * sqrt(2/pi)` —
strictly positive. The underlying gauss is zero-mean; the slippage
applied is not.

The wording invited exactly the wrong conclusion: that slippage cancels
out over many fills and can be ignored in aggregate. Over N fills the
expected cost is `N * price * spread * sqrt(2/pi)`, and on an
accumulation platform doing thousands of small fills that is not a
rounding error.

WHY SN-18 IS CLOSED AS NOT-A-DEFECT
A sim audit on 2026-08-07 concluded that because `abs()` makes slippage
one-directional, a LIMIT placed at the slipped price ALWAYS crosses, and
called that a defect in the resting-order model.

The chain is real; the conclusion is not. `scrumming_bot.py:10929`
documents it: "For LIMIT orders the exec_price below already includes a
-0.1% drift for FAST FILL". The bot deliberately places a MARKETABLE
limit to guarantee execution, and `verify_hit` is the cap that cancels
the order when that drift exceeds per-asset-class tolerance. Limits
crossing is the intended consequence, not a bug.

Removing the `abs()` would make live orders less likely to fill — a
strategy change degrading execution on a live fleet, dressed as a fix.

What IS true is narrower: Fleet's resting-order model is never exercised
by the fleet, because the fleet never places a non-marketable limit.
That is a coverage gap in the harness, not a correctness defect. The
resting code works and is pinned directly by
tests/test_fleet_sim_infrastructure.py.
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
SPREAD = 0.001          # 0.1%
N = 20_000


def _draws(side, spread=SPREAD, seed=20260807):
    random.seed(seed)
    return [fill_price(PRICE, side, spread=spread) for _ in range(N)]


class TestTheInstrumentWorks:
    def test_the_draw_actually_varies(self):
        """POSITIVE CONTROL. If fill_price returned a constant, every
        directional assertion below would hold vacuously."""
        assert len(set(_draws("buy"))) > 100


class TestSlippageIsAlwaysAgainstTheTrader:
    def test_a_buy_never_fills_below_the_intended_price(self):
        assert min(_draws("buy")) >= PRICE - 1e-12

    def test_a_sell_never_fills_above_the_intended_price(self):
        assert max(_draws("sell")) <= PRICE + 1e-12

    def test_the_mean_cost_is_positive_not_zero(self):
        """THE correction. A zero-mean model would centre on PRICE; this
        one is displaced by spread*sqrt(2/pi) in the adverse direction,
        every time, in both directions of trade."""
        expected = PRICE * SPREAD * math.sqrt(2.0 / math.pi)
        buys = _draws("buy")
        mean_cost = sum(buys) / len(buys) - PRICE
        assert mean_cost > 0.0, "slippage averaged to zero or better"
        assert mean_cost == pytest.approx(expected, rel=0.10), (
            f"mean adverse slippage {mean_cost:.6f} does not match the "
            f"half-normal expectation {expected:.6f}")

    def test_it_does_not_cancel_out_over_many_fills(self):
        """The claim the old docstring invited. On an accumulation
        platform doing thousands of small fills, this is the difference
        between a rounding error and a real cost."""
        buys = _draws("buy")
        total_cost = sum(b - PRICE for b in buys)
        assert total_cost > 0.0
        # Scales with N rather than staying bounded, which is what
        # "averages out" would predict.
        half = _draws("buy", seed=20260807)[: N // 2]
        half_cost = sum(b - PRICE for b in half)
        assert total_cost > half_cost * 1.5


class TestZeroAndDegenerateInputs:
    @pytest.mark.parametrize("bad", [0.0, -1.0])
    def test_a_nonpositive_price_is_returned_unchanged(self, bad):
        assert fill_price(bad, "buy") == bad

    def test_a_zero_spread_produces_no_slippage(self):
        """NEGATIVE CONTROL: the adverse displacement must come from the
        spread, not from a constant baked into the function."""
        assert fill_price(PRICE, "buy", spread=0.0) == pytest.approx(PRICE)
        assert fill_price(PRICE, "sell", spread=0.0) == pytest.approx(PRICE)


class TestTheDocstringMatchesTheDistribution:
    def test_it_no_longer_claims_zero_mean_slippage(self):
        """A docstring saying slippage averages out, attached to a model
        that guarantees it does not, is the kind of line a cold read
        trusts instead of re-deriving."""
        doc = fill_price.__doc__ or ""
        _first = doc.split(".", 1)[0]
        assert "zero-mean" not in _first.lower(), (
            "the opening line still calls this a zero-mean draw; the "
            "applied slippage has mean spread*sqrt(2/pi) > 0")

    def test_it_records_why_the_limits_cross(self):
        """SN-18 was closed on this reasoning. If the note goes, the
        next audit re-derives 'limits always cross' and calls it a bug
        again."""
        doc = fill_price.__doc__ or ""
        assert "marketable" in doc.lower()
