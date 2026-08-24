"""The fold must acquire enough to BACK the compounding it triggers (M1).

THE DEFECT
Manual Fire sized its fold buy from ``-delta_usd`` against
``_target_balance``, and only AFTER the fill did
``_apply_fold_target_growth`` raise that target. So position landed on
target_OLD while the target became target_OLD + growth: the residual
deficit was IDENTICALLY the growth, and the fold logged success having
structurally failed to re-zero.

WHY IT COULD NEVER BE WORKED OFF
Growth caps at 1% of ANCHOR (`:1418`) and `target >= anchor` is a setter
invariant, while Manual Fire's own no-op band is 1% of TARGET (`:9248`).
So the residual is ALWAYS inside the dust band -- firing again returns
"already within dust band. No-op." The miss is permanent, silent, and
invisible to the very tool meant to correct it.

OPERATOR RULING, 2026-08-07:
    "After growth is calculated so that the Fold does not acquire too
     little and actually fails to compound."

The growth must be backed by POSITION, not left in the wallet as cash.
That is the cash-vs-portfolio frame error the open item named.

WHY A FIXED POINT
Buying more units discharges more tranches, which yields more growth.
The feedback term is bounded by the cycle cap and strictly decreasing,
so it converges in one or two passes.
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


def _bot(tranches=None, *, anchor=100.0, target=100.0, cap_pct=1.0,
         consumed=0.0, pool=0.0, active=True, qrate=1.0):
    b = object.__new__(ScrummingBot)
    b.bot_id = "b1"
    b.config = type("C", (), {
        "max_target_growth_pct": cap_pct,
        "profit_folding_active": active,
        "symbol": "BTC/USD",
    })()
    b._fold_tranches = list(tranches or [])
    b._anchor_target_balance = anchor
    b._target_balance = target
    b._fold_cycle_cap_consumed = consumed
    b._standing_surplus_usd = pool
    b._quote_to_usd = qrate
    b._fold_accumulator = 0.0
    b._target_grow_last_side = None
    b.stats = type("S", (), {})()
    # The stub must ACCEPT the bus signature -- it takes 12 real
    # calls of the form emit("bot.log", bot_id=..., message=...).
    # Production wraps every emit in try/except-debug, so dropping
    # these parameters would break the stub silently. Keep them;
    # the leading underscore marks the names deliberately unused.
    b._bus = type("B", (), {"emit": lambda self, *_a, **_k: None})()
    return b


def _tr(units, ref, usd=None):
    return {"units": units, "ref": ref, "usd": usd if usd is not None
            else units * ref}


class TestTheInstrumentWorks:
    def test_a_profitable_tranche_previews_growth(self):
        """POSITIVE CONTROL. Every assertion below assumes the preview
        can be non-zero at all."""
        b = _bot([_tr(1.0, 60.0)])
        assert b._preview_fold_growth(1.0, 50.0) == pytest.approx(1.0)

    def test_no_tranches_previews_nothing(self):
        """NEGATIVE CONTROL: it must not invent growth from nowhere."""
        assert _bot([])._preview_fold_growth(1.0, 50.0) == 0.0


class TestItMatchesTheRealFormula:
    """If the preview and the applier disagree, the fold is sized for a
    growth that never lands -- replacing an undershoot with an
    overshoot."""

    @pytest.mark.parametrize("units,price,ref", [
        (1.0, 50.0, 60.0), (2.0, 10.0, 12.5), (0.5, 100.0, 140.0),
    ])
    def test_preview_equals_what_apply_actually_adds(self, units, price, ref):
        tranches = [_tr(units, ref)]
        preview = _bot(list(tranches))._preview_fold_growth(units, price)

        applier = _bot(list(tranches))
        before = applier._target_balance
        # The real path accumulates take x (ref - fill_price) itself.
        accum = units * (ref - price) if ref > price else 0.0
        applied = applier._apply_fold_target_growth(accum, "TEST")
        assert preview == pytest.approx(applied)
        assert applier._target_balance - before == pytest.approx(preview)

    def test_the_cycle_cap_bounds_the_preview(self):
        """Cap = anchor x pct/100 = $1.00 here; surplus is $10."""
        b = _bot([_tr(1.0, 60.0)], anchor=100.0, cap_pct=1.0)
        assert b._preview_fold_growth(1.0, 50.0) == pytest.approx(1.0)

    def test_a_consumed_cap_previews_nothing(self):
        b = _bot([_tr(1.0, 60.0)], anchor=100.0, cap_pct=1.0, consumed=1.0)
        assert b._preview_fold_growth(1.0, 50.0) == 0.0

    def test_the_standing_pool_is_an_input(self):
        """A break-even fold can still grow the target by draining the
        pool, so the preview must see it or it under-sizes."""
        b = _bot([_tr(1.0, 50.0)], anchor=100.0, cap_pct=1.0, pool=5.0)
        assert b._preview_fold_growth(1.0, 50.0) == pytest.approx(1.0)

    def test_folding_switched_off_previews_nothing(self):
        b = _bot([_tr(1.0, 60.0)], active=False)
        assert b._preview_fold_growth(1.0, 50.0) == 0.0

    def test_only_units_actually_bought_count(self):
        """Growth is bounded by what the buy discharges, not by the
        whole queue."""
        # Issue #106 - the TARGET is what lifts the cap out of the way
        # now, so it is raised with the anchor. The old fixture raised
        # only the anchor and left the target at $100, which is a state
        # the setter invariant `target >= anchor` forbids: the cap was
        # being lifted by a bot that could not exist.
        b = _bot([_tr(10.0, 60.0)], anchor=10000.0, target=10000.0)
        assert b._preview_fold_growth(1.0, 50.0) == pytest.approx(10.0)

    def test_a_tranche_below_the_price_adds_nothing(self):
        """Buying back ABOVE the sell price is a loss, not surplus."""
        assert _bot([_tr(1.0, 40.0)])._preview_fold_growth(1.0, 50.0) == 0.0


class TestPreviewingChangesNothing:
    def test_it_does_not_move_the_target(self):
        b = _bot([_tr(1.0, 60.0)])
        b._preview_fold_growth(1.0, 50.0)
        assert b._target_balance == pytest.approx(100.0)

    def test_it_does_not_consume_the_cap(self):
        b = _bot([_tr(1.0, 60.0)])
        b._preview_fold_growth(1.0, 50.0)
        assert b._fold_cycle_cap_consumed == 0.0

    def test_it_does_not_drain_the_standing_pool(self):
        b = _bot([_tr(1.0, 50.0)], pool=5.0)
        b._preview_fold_growth(1.0, 50.0)
        assert b._standing_surplus_usd == pytest.approx(5.0)

    def test_it_does_not_reorder_the_live_queue(self):
        """The real discharge sorts highest-ref-first in place. Sorting
        during a PREVIEW would change which tranches a later real fold
        consumes."""
        b = _bot([_tr(1.0, 10.0), _tr(1.0, 90.0)])
        before = [t["ref"] for t in b._fold_tranches]
        b._preview_fold_growth(2.0, 5.0)
        assert [t["ref"] for t in b._fold_tranches] == before

    def test_it_does_not_consume_tranche_units(self):
        b = _bot([_tr(3.0, 60.0)])
        b._preview_fold_growth(3.0, 50.0)
        assert b._fold_tranches[0]["units"] == pytest.approx(3.0)


class TestDegenerateInputs:
    @pytest.mark.parametrize("units,price", [(0.0, 50.0), (1.0, 0.0),
                                             (-1.0, 50.0), (1.0, -5.0)])
    def test_no_crash_and_no_growth(self, units, price):
        assert _bot([_tr(1.0, 60.0)])._preview_fold_growth(units, price) == 0.0

    def test_junk_queue_entries_are_skipped(self):
        b = _bot()
        b._fold_tranches = [_tr(1.0, 60.0), "not-a-dict", None]
        assert b._preview_fold_growth(1.0, 50.0) == pytest.approx(1.0)

    def test_the_quote_rate_is_applied(self):
        # Issue #106 - same reason as above: the target carries the
        # cap now, and target < anchor is not a reachable state.
        b = _bot([_tr(1.0, 60.0)], anchor=10000.0, target=10000.0,
                 qrate=3.0)
        assert b._preview_fold_growth(1.0, 50.0) == pytest.approx(30.0)


class TestTheSizingActuallyUsesIt:
    """A preview nothing consults fixes nothing."""

    def _fold_branch(self):
        import src.trading.scrumming_bot as m

        src = Path(m.__file__).read_text(encoding="utf-8")
        fn = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and n.name == "_execute_manual_rebalance")
        return fn, src

    def test_manual_fire_calls_the_preview(self):
        fn, _ = self._fold_branch()
        calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
                 and getattr(n.func, "attr", "") == "_preview_fold_growth"]
        assert calls, "the fold still sizes against the pre-growth target"

    def test_the_buy_target_is_no_longer_the_bare_delta(self):
        """Asserted structurally: `buy_usd_target = -delta_usd` alone is
        exactly the defect."""
        fn, src = self._fold_branch()
        for n in ast.walk(fn):
            if (isinstance(n, ast.Assign)
                    and any(getattr(t, "id", "") == "buy_usd_target"
                            for t in n.targets)):
                seg = ast.get_source_segment(src, n.value) or ""
                assert seg.strip() != "-delta_usd", \
                    "buy_usd_target must include the prospective growth"

    def test_the_preview_runs_before_the_order(self):
        """Sizing after the order would be no fix at all."""
        fn, _ = self._fold_branch()
        prev = [n.lineno for n in ast.walk(fn) if isinstance(n, ast.Call)
                and getattr(n.func, "attr", "") == "_preview_fold_growth"]
        orders = [n.lineno for n in ast.walk(fn) if isinstance(n, ast.Call)
                  and getattr(n.func, "attr", "") == "guarded_place_order"]
        assert prev and orders and min(prev) < max(orders)

    def test_growth_is_still_applied_exactly_once_after_the_fill(self):
        """Sizing for the growth must not ALSO double-apply it."""
        fn, _ = self._fold_branch()
        applies = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
                   and getattr(n.func, "attr", "") ==
                   "_apply_fold_target_growth"]
        assert len(applies) == 1, \
            f"expected one growth application, found {len(applies)}"
