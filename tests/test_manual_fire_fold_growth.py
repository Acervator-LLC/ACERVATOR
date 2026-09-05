"""Manual Fire sizes its fold buy against the target it is about to grow.

``_preview_fold_growth`` reports the growth the queued ``_fold_tranches``
will yield at the fill price, and ``_execute_manual_rebalance`` adds it to
the deficit before it places the buy. ``_apply_fold_target_growth`` then
raises ``_target_balance`` by the same amount once the fill lands, so the
position ends on the grown target and not below it.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading.scrumming_bot import ScrummingBot  # noqa: E402


def _bot(
    tranches=None,
    *,
    anchor=100.0,
    target=100.0,
    cap_pct=1.0,
    consumed=0.0,
    pool=0.0,
    active=True,
    qrate=1.0,
):
    b = object.__new__(ScrummingBot)
    b.bot_id = "b1"
    b.config = type(
        "C",
        (),
        {
            "max_target_growth_pct": cap_pct,
            "profit_folding_active": active,
            "symbol": "BTC/USD",
        },
    )()
    b._fold_tranches = list(tranches or [])
    b._anchor_target_balance = anchor
    b._target_balance = target
    b._fold_cycle_cap_consumed = consumed
    b._standing_surplus_usd = pool
    b._quote_to_usd = qrate
    b._fold_accumulator = 0.0
    b._target_grow_last_side = None
    b.stats = type("S", (), {})()
    # Production wraps every emit in try/except, so a stub that refuses one is silent.
    b._bus = type("B", (), {"emit": lambda self, *_a, **_k: None})()
    return b


def _tr(units, ref, usd=None):
    return {"units": units, "ref": ref, "usd": usd if usd is not None else units * ref}


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

    @pytest.mark.parametrize(
        "units,price,ref",
        [
            (1.0, 50.0, 60.0),
            (2.0, 10.0, 12.5),
            (0.5, 100.0, 140.0),
        ],
    )
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
        # The target is raised with the anchor: the setter forbids target below anchor.
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
    @pytest.mark.parametrize(
        "units,price", [(0.0, 50.0), (1.0, 0.0), (-1.0, 50.0), (1.0, -5.0)]
    )
    def test_no_crash_and_no_growth(self, units, price):
        assert _bot([_tr(1.0, 60.0)])._preview_fold_growth(units, price) == 0.0

    def test_junk_queue_entries_are_skipped(self):
        b = _bot()
        b._fold_tranches = [_tr(1.0, 60.0), "not-a-dict", None]
        assert b._preview_fold_growth(1.0, 50.0) == pytest.approx(1.0)

    def test_the_quote_rate_is_applied(self):
        # The target carries the cap, and target below anchor is unreachable.
        b = _bot([_tr(1.0, 60.0)], anchor=10000.0, target=10000.0, qrate=3.0)
        assert b._preview_fold_growth(1.0, 50.0) == pytest.approx(30.0)


class _Order:
    id = "fold-1"
    filled = 0.0
    amount = 0.0
    price = 1.0


class _Ticker:
    def __init__(self, last):
        self.last = last


def _fire_bot(tranches, *, holdings=90.0, target=100.0, price=1.0, cap_pct=1.0):
    """A bot the real ``_execute_manual_rebalance`` runs against.

    Only the outward edges are stubbed, and ``seen`` records the order
    the shipping code called ``_preview_fold_growth``,
    ``guarded_place_order`` and ``_apply_fold_target_growth`` in.
    """
    bot = _bot(tranches, anchor=target, target=target, cap_pct=cap_pct)
    bot.config.exchange_id = "coinbase"
    bot.config.target_asset = "BTC"
    bot.seen = []
    bot.placed = []
    bot._current_holdings = holdings
    bot._manual_fire_pending = True
    bot._fold_queue_usd = 0.0
    bot._main_lots = []
    bot._tranches_closed_lifetime = 0
    bot._last_trade_side = None
    bot._last_trade_price = 0.0
    bot.stats.total_trades = 0
    bot.stats.total_folded_usd = 0.0

    real_preview = bot._preview_fold_growth
    real_growth = bot._apply_fold_target_growth

    def _preview(units, at_price):
        bot.seen.append("preview")
        return real_preview(units, at_price)

    def _growth(profit_usd, source):
        bot.seen.append("growth")
        return real_growth(profit_usd, source=source)

    async def _refresh():
        return 1.0

    async def _balance(*_args):
        return type("B", (), {"total": 1e6, "free": 1e6, "absent": False})()

    async def _place(**kwargs):
        bot.seen.append("order")
        bot.placed.append(kwargs)
        return _Order()

    async def _settled(_order, _symbol, requested, _tick_price):
        return requested, price, True

    bot._preview_fold_growth = _preview
    bot._apply_fold_target_growth = _growth
    bot._refresh_quote_to_usd = _refresh
    bot._get_balance = _balance
    bot.guarded_place_order = _place
    bot._settled_fill = _settled
    bot.reset_swos_cycle = lambda: None
    bot._reset_opposing_hysteresis_after_fill = lambda: None
    bot._emit_voting_panel_snapshot_at_fire = lambda **_kw: None
    bot._emit_gate_decision_at_fire = lambda **_kw: None
    return bot


def _fire(bot, price=1.0):
    """One ``_fire_bot`` run through the real fold path."""
    asyncio.run(bot._execute_manual_rebalance(_Ticker(price), "manual_button"))
    return bot


class TestTheSizingActuallyUsesIt:
    """A preview nothing consults fixes nothing."""

    def test_a_fold_with_no_queue_buys_the_bare_deficit(self):
        """POSITIVE CONTROL. ``_preview_fold_growth`` returns zero with an
        empty queue, and ``guarded_place_order`` is asked for the bare
        deficit."""
        bot = _fire(_fire_bot([]))
        assert bot.placed, "no order was placed; nothing was driven"
        assert bot.placed[0]["amount"] == pytest.approx(10.0)

    def test_the_fold_buys_the_post_growth_size(self):
        """``guarded_place_order`` is asked for the deficit plus the
        growth ``_preview_fold_growth`` reports."""
        bot = _fire(_fire_bot([_tr(1.0, 2.0)]))
        assert bot.placed[0]["amount"] == pytest.approx(11.0)

    def test_the_fold_lands_the_position_on_the_grown_target(self):
        """``_current_holdings`` reaches ``_target_balance`` after
        ``_apply_fold_target_growth`` has raised it."""
        bot = _fire(_fire_bot([_tr(1.0, 2.0)]))
        landed = bot._current_holdings * 1.0 * bot._quote_to_usd
        assert bot._target_balance == pytest.approx(101.0)
        assert landed == pytest.approx(bot._target_balance)

    def test_the_preview_runs_before_the_order(self):
        """``_preview_fold_growth`` is called before
        ``guarded_place_order``."""
        bot = _fire(_fire_bot([_tr(1.0, 2.0)]))
        assert "preview" in bot.seen, bot.seen
        assert bot.seen.index("preview") < bot.seen.index("order"), bot.seen

    def test_growth_is_applied_exactly_once_after_the_fill(self):
        """``_apply_fold_target_growth`` runs once, after
        ``guarded_place_order``."""
        bot = _fire(_fire_bot([_tr(1.0, 2.0)]))
        assert bot.seen.count("growth") == 1, bot.seen
        assert bot.seen.index("order") < bot.seen.index("growth"), bot.seen
