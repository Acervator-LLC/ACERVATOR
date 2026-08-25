"""Phase 2 Step 8 — per-tranche Manual Fire books its compound growth.

THE DEFECT
`manual_fire_tranche` filled a tranche and applied ZERO target growth. It
never called `_apply_fold_target_growth`, so the operator's dominant dip
path contributed nothing to compounding no matter how far below ref it
bought. Live evidence for "dominant": ETH/USD 27 of 27 tranches carry
`operator_initiated`, ORCA/USD 56 of 107.

Its two telemetry emits also carried no profit field at all, so a
profitable manual fold was indistinguishable from a break-even one in
every downstream consumer.

THE FORMULA
Computed in the CASH frame, identical to the autonomous path. For a
single tranche the autonomous formula reduces to it:

    extra_asset  = cost x (1/fill - 1/ref)
    accum_profit = extra_asset x fill = cost x (1 - fill/ref)

Buying at ref yields 0. Buying ABOVE ref yields a negative, which
`_apply_fold_target_growth` floors at 0 -- an unprofitable manual fold
cannot shrink the target.

BLAST RADIUS
This is the step that actually starts moving the number. It is bounded
per cycle by `_cap_remaining`: at most anchor x max_target_growth_pct/100
per bot per cycle, roughly $33 fleet-wide per cycle at the current 1%.
It does not change WHAT is bought or WHEN -- only what is booked after
the buy has already filled.

ORDERING
The growth call sits BEFORE the tranche is dequeued. Booking after
removal is Break 7 in the audit; this path is now correct by
construction.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading.scrumming_bot import ScrummingBot  # noqa: E402

SRC = (REPO_ROOT / "src" / "trading" / "scrumming_bot.py").read_text(encoding="utf-8")


def _fn(name: str):
    for n in ast.walk(ast.parse(SRC)):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    raise AssertionError(f"{name} not found")


def _manual_profit(cost: float, fill_price: float, ref: float) -> float:
    """The cash-frame surplus, as manual_fire_tranche computes it."""
    return cost * (1.0 - fill_price / ref) if ref > 0 else 0.0


class _Bus:
    def __init__(self):
        self.msgs = []

    def emit(self, _ev, **kw):
        self.msgs.append(kw.get("message", ""))


class _Bot:
    _apply_fold_target_growth = ScrummingBot._apply_fold_target_growth

    def __init__(self, anchor=200.0, cap_pct=1.0):
        self.bot_id = "bot-test-0001"
        self.config = type(
            "C", (), {"max_target_growth_pct": cap_pct, "profit_folding_active": True}
        )()
        self._bus = _Bus()
        self._quote_to_usd = 1.0
        self._anchor_target_balance = anchor
        self._target_balance = anchor
        self._fold_cycle_cap_consumed = 0.0
        self._standing_surplus_usd = 0.0
        self._fold_accumulator = 0.0
        self._target_grow_last_side = None
        self.stats = type("S", (), {"standing_surplus_usd": 0.0})()


class TestTheFormula:
    def test_the_plan_fixture(self):
        """ref 1.00, cost 10.00, fill 0.95 -> surplus $0.50."""
        assert _manual_profit(10.0, 0.95, 1.00) == pytest.approx(0.50)

    def test_it_matches_the_autonomous_cash_frame(self):
        """POSITIVE CONTROL on the algebra: cost x (1 - fill/ref) must
        equal extra_asset x fill, which is how the autonomous path
        computes it."""
        cost, fill, ref = 10.0, 0.95, 1.00
        extra_asset = cost * (1.0 / fill - 1.0 / ref)
        assert _manual_profit(cost, fill, ref) == pytest.approx(extra_asset * fill)

    def test_buying_at_ref_yields_nothing(self):
        assert _manual_profit(10.0, 1.00, 1.00) == pytest.approx(0.0)

    def test_buying_above_ref_is_negative_before_the_floor(self):
        """The helper floors it; the formula itself must not pretend."""
        assert _manual_profit(10.0, 1.10, 1.00) < 0


class TestItMovesTheTarget:
    def test_the_plan_fixture_end_to_end(self):
        """anchor 200, cap 1% -> $2.00 budget; a $0.50 surplus lands
        whole. Current code moved the target $0.00."""
        b = _Bot(anchor=200.0, cap_pct=1.0)
        applied = b._apply_fold_target_growth(
            _manual_profit(10.0, 0.95, 1.00), source="MANUAL_TRANCHE_FOLD"
        )
        assert applied == pytest.approx(0.50)
        assert b._target_balance == pytest.approx(200.50)

    def test_an_unprofitable_manual_fold_cannot_shrink_the_target(self):
        """NEGATIVE CONTROL. Booking a negative would let Manual Fire
        REDUCE the target, which nothing else in the system can do."""
        b = _Bot(anchor=200.0)
        applied = b._apply_fold_target_growth(
            _manual_profit(10.0, 1.10, 1.00), source="MANUAL_TRANCHE_FOLD"
        )
        assert applied == 0.0
        assert b._target_balance == pytest.approx(200.0)

    def test_it_is_bounded_by_the_cycle_cap(self):
        """A huge manual fold cannot exceed the per-cycle budget."""
        b = _Bot(anchor=100.0, cap_pct=1.0)
        applied = b._apply_fold_target_growth(
            _manual_profit(1000.0, 0.50, 1.00), source="MANUAL_TRANCHE_FOLD"
        )
        assert applied == pytest.approx(1.0)


class TestTheCallSiteIsWired:
    def test_manual_fire_calls_the_growth_helper(self):
        seg = ast.get_source_segment(SRC, _fn("manual_fire_tranche")) or ""
        assert (
            "_apply_fold_target_growth" in seg
        ), "manual_fire_tranche books no target growth"

    def test_it_uses_the_manual_source_tag(self):
        seg = ast.get_source_segment(SRC, _fn("manual_fire_tranche")) or ""
        assert "MANUAL_TRANCHE_FOLD" in seg

    def test_growth_is_booked_before_the_tranche_is_dequeued(self):
        """Break 7 in the audit. Booking after removal loses the surplus
        if anything between them returns early."""
        seg = ast.get_source_segment(SRC, _fn("manual_fire_tranche")) or ""
        assert seg.index("_apply_fold_target_growth") < seg.index("_removed_ok")

    def test_a_booking_failure_cannot_raise_over_a_filled_buy(self):
        """The order has already executed by this point. A bookkeeping
        exception must not propagate back over a completed fill.

        Located via the AST rather than a text window: the explanatory
        comment above the call also names the helper, and anchoring on
        the first textual match put the window in the wrong place."""
        fn = _fn("manual_fire_tranche")
        guarded = False
        for node in ast.walk(fn):
            if not isinstance(node, ast.Try):
                continue
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Call)
                    and getattr(inner.func, "attr", "") == "_apply_fold_target_growth"
                ):
                    guarded = bool(node.handlers)
        assert guarded, (
            "the growth call is not inside a try/except; a bookkeeping "
            "exception would propagate back over an already-filled buy"
        )

    def test_both_emits_carry_the_profit(self):
        """They carried no profit field, so a profitable manual fold was
        indistinguishable from a break-even one downstream."""
        seg = ast.get_source_segment(SRC, _fn("manual_fire_tranche")) or ""
        assert seg.count('"growth_applied"') >= 2
        assert seg.count('"accum_profit"') >= 2
