"""The standing surplus pool, its outlet and its clear.

``_apply_fold_target_growth`` releases ``_standing_surplus_usd`` up to
``cycle_growth_cap_usd`` on every fold, a break-even fold included, and
parks what the cap will not take. ``_execute_detonation`` zeroes
``_standing_surplus_usd`` and adds the abandoned tranches to
``_tranches_discarded_lifetime``, leaving ``_tranches_closed_lifetime``
and ``_fold_cycle_cap_consumed`` where they were.
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


class _Bus:
    def __init__(self):
        self.msgs = []

    def emit(self, _ev, **kw):
        self.msgs.append(kw.get("message", ""))

    def text(self):
        return "\n".join(self.msgs)


class _Bot:
    """Only what _apply_fold_target_growth reads."""

    _apply_fold_target_growth = ScrummingBot._apply_fold_target_growth

    cycle_growth_cap_usd = ScrummingBot.cycle_growth_cap_usd

    def __init__(
        self, *, anchor=200.0, cap_pct=1.0, consumed=0.0, pool=0.0, target=None
    ):
        self.bot_id = "bot-test-0001"
        self.config = type(
            "C", (), {"max_target_growth_pct": cap_pct, "profit_folding_active": True}
        )()
        self._bus = _Bus()
        self._quote_to_usd = 1.0
        self._anchor_target_balance = anchor
        self._target_balance = anchor if target is None else target
        self._fold_cycle_cap_consumed = consumed
        self._standing_surplus_usd = pool
        self._fold_accumulator = 0.0
        self._target_grow_last_side = None
        self.stats = type("S", (), {"standing_surplus_usd": 0.0})()


class TestTheHelperWorks:
    def test_a_plain_surplus_grows_the_target(self):
        """POSITIVE CONTROL. If growth never applied, every drain
        assertion below would pass against a broken helper."""
        b = _Bot()
        applied = b._apply_fold_target_growth(0.50, source="TEST")
        assert applied == pytest.approx(0.50)
        assert b._target_balance == pytest.approx(200.50)


class TestTheDrain:
    def test_the_plan_fixture(self):
        """pool 5.0, cap_remaining 2.0, surplus 0.5 -> applied 2.0,
        pool 3.5. Current code gave applied 0.5 and pool unchanged."""
        b = _Bot(anchor=200.0, cap_pct=1.0, consumed=0.0, pool=5.0)
        # cap = 200 * 1% = 2.00
        applied = b._apply_fold_target_growth(0.5, source="TEST")
        assert applied == pytest.approx(2.0)
        assert b._standing_surplus_usd == pytest.approx(3.5)

    def test_the_target_moved_by_the_applied_amount(self):
        b = _Bot(anchor=200.0, pool=5.0)
        b._apply_fold_target_growth(0.5, source="TEST")
        assert b._target_balance == pytest.approx(202.0)

    def test_a_break_even_fold_still_drains_the_pool(self):
        """THE second half. Zero new surplus used to return before the
        drain, so parked money was released only by a PROFITABLE fold --
        and the code's own message says break-even is the expected
        case."""
        b = _Bot(anchor=200.0, pool=5.0)
        applied = b._apply_fold_target_growth(0.0, source="TEST")
        assert applied == pytest.approx(2.0)
        assert b._standing_surplus_usd == pytest.approx(3.0)

    def test_nothing_new_and_nothing_parked_is_still_a_skip(self):
        """NEGATIVE CONTROL: the relaxed guard must not turn every
        break-even fold into a log line and a no-op write."""
        b = _Bot(anchor=200.0, pool=0.0)
        applied = b._apply_fold_target_growth(0.0, source="TEST")
        assert applied == 0.0
        assert "COMPOUND SKIPPED" in b._bus.text()

    def test_a_small_pool_drains_fully(self):
        """The real fleet case: $0.6289 parked against a $1.00 cap."""
        b = _Bot(anchor=100.0, cap_pct=1.0, pool=0.6289)
        applied = b._apply_fold_target_growth(0.0, source="TEST")
        assert applied == pytest.approx(0.6289)
        assert b._standing_surplus_usd == pytest.approx(0.0)

    def test_the_cap_still_bounds_growth(self):
        """NEGATIVE CONTROL. The drain must not let a large pool exceed
        the per-cycle cap -- that is the whole safety property."""
        b = _Bot(anchor=100.0, cap_pct=1.0, pool=999.0)
        applied = b._apply_fold_target_growth(50.0, source="TEST")
        assert applied == pytest.approx(1.0)
        assert b._target_balance == pytest.approx(101.0)

    def test_consumed_cap_still_parks_without_draining(self):
        """With no headroom there is nothing to drain into. The parking
        branch is unchanged."""
        b = _Bot(anchor=100.0, cap_pct=1.0, consumed=1.0, pool=5.0)
        applied = b._apply_fold_target_growth(2.0, source="TEST")
        assert applied == 0.0
        assert b._standing_surplus_usd == pytest.approx(7.0)

    def test_the_log_reports_the_drain(self):
        """A growth funded from the pool used to read as though it came
        from the fold."""
        b = _Bot(anchor=200.0, pool=5.0)
        b._apply_fold_target_growth(0.5, source="TEST")
        msg = b._bus.text()
        assert "standing" in msg
        assert "drained" in msg


class _Order:
    id = "det-1"
    filled = 900.0
    average_price = 1.0
    price = 1.0


class _Ticker:
    last = 1.0


class _DetBot:
    """A bot the real ``_execute_detonation`` runs against.

    ``guarded_place_order`` and ``_route_scrum_proceeds_via_wires``
    record their arguments, and every counter starts non-zero.
    """

    _execute_detonation = ScrummingBot._execute_detonation

    def __init__(self, *, tranches=3, pool=7.5, holdings=1000.0, anchor=100.0):
        self.bot_id = "bot-test-0001"
        self.config = type("C", (), {"symbol": "BIO/USD", "target_asset": "BIO"})()
        self._bus = _Bus()
        self._quote_to_usd = 1.0
        self._current_holdings = holdings
        self._anchor_target_balance = anchor
        self._target_balance = anchor + 25.0
        self._fold_tranches = [
            {"units": 1.0, "ref": 2.0, "usd": 2.0} for _ in range(tranches)
        ]
        self._fold_queue_usd = float(tranches) * 2.0
        self._standing_surplus_usd = pool
        self._fold_cycle_cap_consumed = 0.75
        self._tranches_discarded_lifetime = 4
        self._tranches_closed_lifetime = 11
        self._main_lots = [{"units": holdings, "initial_buy_price": 0.5}]
        self._last_trade_price = 0.0
        self.stats = type("S", (), {"standing_surplus_usd": pool, "total_trades": 6})()
        self.placed = []
        self.routed = []
        self.fired = []

    async def guarded_place_order(self, **kwargs):
        self.placed.append(kwargs)
        return _Order()

    def _route_scrum_proceeds_via_wires(self, scrum_usd, sell_fill, label):
        self.routed.append((scrum_usd, sell_fill, label))
        return 0.0

    def _emit_voting_panel_snapshot_at_fire(self, side, trade_action):
        self.fired.append(("snapshot", side, trade_action))

    def _emit_gate_decision_at_fire(self, side, trade_action):
        self.fired.append(("gate", side, trade_action))


def _detonate(**kwargs):
    """One ``_DetBot`` run through the real ``_execute_detonation``."""
    bot = _DetBot(**kwargs)
    asyncio.run(bot._execute_detonation(_Ticker()))
    return bot


class TestDetonationHygiene:
    def test_the_detonation_actually_sells(self):
        """POSITIVE CONTROL. ``guarded_place_order`` ran and
        ``_fold_tranches`` emptied."""
        bot = _detonate()
        assert bot.placed, "no order was placed, so nothing was driven"
        assert bot.placed[0]["side"].value == "sell"
        assert bot._fold_tranches == []
        assert bot._target_balance == pytest.approx(bot._anchor_target_balance)

    def test_a_refused_price_leaves_every_counter_alone(self):
        """NEGATIVE CONTROL: a zero ticker price leaves
        ``_standing_surplus_usd`` and ``_tranches_discarded_lifetime``
        where they were."""
        bot = _DetBot()
        ticker = _Ticker()
        ticker.last = 0.0
        asyncio.run(bot._execute_detonation(ticker))
        assert bot.placed == []
        assert bot._standing_surplus_usd == pytest.approx(7.5)
        assert bot._tranches_discarded_lifetime == 4
        assert len(bot._fold_tranches) == 3

    def test_the_clear_counts_discarded_not_closed(self):
        """``_tranches_discarded_lifetime`` takes the abandoned tranches
        and ``_tranches_closed_lifetime`` does not move."""
        bot = _detonate(tranches=3)
        assert bot._tranches_discarded_lifetime == 7
        assert bot._tranches_closed_lifetime == 11

    def test_the_discarded_count_follows_the_queue_it_abandoned(self):
        """``_tranches_discarded_lifetime`` moves by the length of
        ``_fold_tranches``, never by a fixed step."""
        assert _detonate(tranches=5)._tranches_discarded_lifetime == 9
        assert _detonate(tranches=0)._tranches_discarded_lifetime == 4

    def test_it_zeroes_the_standing_pool(self):
        """``_standing_surplus_usd`` and ``stats.standing_surplus_usd``
        both reach zero."""
        bot = _detonate(pool=7.5)
        assert bot._standing_surplus_usd == pytest.approx(0.0)
        assert bot.stats.standing_surplus_usd == pytest.approx(0.0)

    def test_it_does_NOT_clear_the_cycle_cap(self):
        """NEGATIVE CONTROL. ``_fold_cycle_cap_consumed`` keeps its
        value."""
        bot = _detonate()
        assert bot._fold_cycle_cap_consumed == pytest.approx(0.75)
