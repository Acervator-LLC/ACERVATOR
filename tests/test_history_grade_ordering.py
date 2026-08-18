"""History grades must be computed with time running the right way.

C52 / finding NF-16.

THE DEFECT
`history_tab._grade_row` splits the page around the graded row:

    if j < row_i:  same_sym_prior_prices.append(op)   # "before"
    elif j > row_i: same_sym_future_prices.append(op) # "after"

That is only correct if the page is oldest-first. It is not.
`history_helpers.py:295` sorts the fetch:

    all_trades.sort(key=lambda r: r.get("timestamp", 0), reverse=True)

Newest-first. Nothing re-sorts between there and the grader:
`_all_trades` is assigned verbatim, `_filtered` preserves its order, and
`_render_page` slices it. So a LOWER index is a LATER trade, and both
halves were inverted: "prior" held prices from after the trade, "future"
held prices from before it.

WHY IT MATTERS MORE THAN "GRADES ARE A BIT OFF"
The two error directions do not cancel. On the fixture below — a buy at
100 that was immediately followed by a fall to 90 — the correct grade is
**D** and the inverted one is **A+**. The bug hands the best available
grade to one of the worst available trades, and the operator has been
reading those grades as feedback.

WHY THE OBVIOUS FIXTURE DOES NOT WORK
Flipping the axis inverts BOTH sub-scores, and `grade_trade` takes their
unweighted mean, so a symmetric fixture scores identically either way
(exec 1.0/timing 0.0 vs exec 0.0/timing 1.0 both mean 0.5 -> D). The
fixture here is deliberately asymmetric: the graded row sits near the
top of the page, so the inverted reading finds only TWO "prior" prices,
falls below the `>= 3` minimum, and drops the execution axis entirely --
changing the denominator, not just the numerator.
"""
from __future__ import annotations

import statistics
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.history_tab import HistoryTab  # noqa: E402
from src.trading.trade_grader import (  # noqa: E402
    PriceContext,
    TradeRecord,
    grade_trade,
)

SYM = "BTC/USD"

# Newest-first, exactly as history_helpers sorts it.
# index 0 is the most RECENT trade.
PAGE = [
    {"id": "n2", "symbol": SYM, "side": "BUY", "price": 90.0,  "amount": 1.0},
    {"id": "n1", "symbol": SYM, "side": "BUY", "price": 92.0,  "amount": 1.0},
    {"id": "me", "symbol": SYM, "side": "BUY", "price": 100.0, "amount": 1.0},
    {"id": "o1", "symbol": SYM, "side": "BUY", "price": 101.0, "amount": 1.0},
    {"id": "o2", "symbol": SYM, "side": "BUY", "price": 102.0, "amount": 1.0},
    {"id": "o3", "symbol": SYM, "side": "BUY", "price": 103.0, "amount": 1.0},
    {"id": "o4", "symbol": SYM, "side": "BUY", "price": 104.0, "amount": 1.0},
    {"id": "o5", "symbol": SYM, "side": "BUY", "price": 105.0, "amount": 1.0},
]
ROW_I = 2
NEWER = [90.0, 92.0]                          # after the trade
OLDER = [101.0, 102.0, 103.0, 104.0, 105.0]   # before the trade


class _Unbound:
    """`_grade_row` reads no instance state, so it is called UNBOUND
    with `self=None`.

    `object.__new__(HistoryTab)` raises — Qt overrides `__new__` — and
    constructing a real HistoryTab would drag in a QApplication and a
    bot manager for a function that touches neither.
    """

    @staticmethod
    def _grade_row(row_i, page_rows, r):
        return HistoryTab._grade_row(None, row_i, page_rows, r)


def _tab():
    return _Unbound


def _record():
    return TradeRecord(trade_id="me", timestamp=None, asset="BTC",
                       side="buy", price=100.0, quantity=1.0, fee=0.0)


def _expected_letter():
    """Hand-derived: ref from the OLDER rows, future from the NEWER."""
    ctx = PriceContext(
        ref_price_at_decision=statistics.median(OLDER[:5]),
        future_prices=NEWER, regime_tag="LIVE")
    return grade_trade(_record(), ctx).overall


def _inverted_letter():
    """What the page yields when the axis runs backwards: only two
    'prior' prices, so the execution axis is skipped entirely."""
    ctx = PriceContext(ref_price_at_decision=None,
                       future_prices=OLDER, regime_tag="LIVE")
    return grade_trade(_record(), ctx).overall


class TestTheFixtureDiscriminates:
    """POSITIVE CONTROL. If the two readings graded the same, this file
    could not detect the defect and every assertion below would be
    theatre — which is exactly what a symmetric fixture produces here."""

    def test_the_two_readings_disagree(self):
        assert _expected_letter() != _inverted_letter()

    def test_the_correct_reading_is_the_harsh_one(self):
        """A buy at 100 immediately followed by a fall to 90 is a bad
        trade. Anything generous is the inverted answer."""
        assert _expected_letter() == "D"
        assert _inverted_letter() == "A+"


class TestGradeUsesTheRealTimeAxis:
    def test_the_page_row_grades_as_the_hand_derived_letter(self):
        """THE exit-gate measurement."""
        got = _tab()._grade_row(ROW_I, PAGE, PAGE[ROW_I])
        assert got == _expected_letter(), (
            f"grade {got!r} does not match the hand-derived "
            f"{_expected_letter()!r} for a newest-first page")

    def test_it_is_not_the_inverted_letter(self):
        """Stated separately so a regression reads unambiguously."""
        assert _tab()._grade_row(ROW_I, PAGE, PAGE[ROW_I]) \
            != _inverted_letter()

    def test_both_halves_were_flipped_together(self):
        """Flipping one half alone leaves grades wrong and unflagged
        (C52 step 1). Checked by a fixture where each half on its own
        would still produce the wrong letter."""
        got = _tab()._grade_row(ROW_I, PAGE, PAGE[ROW_I])
        half_a = grade_trade(_record(), PriceContext(
            ref_price_at_decision=statistics.median(OLDER[:5]),
            future_prices=OLDER, regime_tag="LIVE")).overall
        half_b = grade_trade(_record(), PriceContext(
            ref_price_at_decision=None,
            future_prices=NEWER, regime_tag="LIVE")).overall
        assert got != half_a, "future_prices half was not flipped"
        assert got != half_b, "ref_price half was not flipped"


class TestTheRefPriceIsTheNEARESTPriorPrices:
    """Subtlety the flip introduces. The rows arrive newest-first, so
    once `j > row_i` is recognised as the PRIOR side, that list runs
    most-recent-first. `[-5:]` would take the five OLDEST priors; the
    ref price wants the five NEAREST."""

    def test_only_the_nearest_five_priors_are_used(self):
        page = list(PAGE) + [
            {"id": f"anc{k}", "symbol": SYM, "side": "BUY",
             "price": 500.0, "amount": 1.0} for k in range(5)
        ]
        got = _tab()._grade_row(ROW_I, page, page[ROW_I])
        assert got == _expected_letter(), (
            "distant ancient prices moved the ref price; the nearest "
            "five priors should be used")


class TestDegenerateInputs:
    def test_fewer_than_three_priors_skips_execution_not_crashes(self):
        page = PAGE[:4]           # only one older row
        assert _tab()._grade_row(ROW_I, page, page[ROW_I]) is not None

    def test_a_lone_row_does_not_raise(self):
        page = [PAGE[ROW_I]]
        assert _tab()._grade_row(0, page, page[0]) is not None

    def test_other_symbols_are_ignored(self):
        page = list(PAGE)
        page.insert(1, {"id": "eth", "symbol": "ETH/USD", "side": "BUY",
                        "price": 9999.0, "amount": 1.0})
        got = _tab()._grade_row(ROW_I + 1, page, page[ROW_I + 1])
        assert got == _expected_letter()

    @pytest.mark.parametrize("bad", [
        {"symbol": SYM, "side": "BUY", "price": 0.0, "amount": 1.0},
        {"symbol": SYM, "side": "BUY", "price": 100.0, "amount": 0.0},
        {"symbol": SYM, "side": "HOLD", "price": 100.0, "amount": 1.0},
    ])
    def test_ungradeable_rows_return_the_dash(self, bad):
        assert _tab()._grade_row(0, [bad], bad) == "—"
