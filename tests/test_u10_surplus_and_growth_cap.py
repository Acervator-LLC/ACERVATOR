"""Issue #133 unit 10 -- the surplus arithmetic and the growth cap.

TWO QUESTIONS, AND WHAT A FAILURE OF EACH CHECK WOULD MEAN.

  1. IS AVAILABLE SURPLUS CALCULATED CORRECTLY? A failure in
     ``TestTheSurplusArithmetic`` means fold profit is being created or
     destroyed between the pool and the target: the applier's inputs
     (this fold's profit, the standing pool) no longer equal its
     outputs (the growth applied, the pool that survives).

  2. DOES THE GROWTH CAP UPDATE AFTER A FOLD WITH SURPLUS? A failure in
     ``TestTheCapStepsOncePerCycle`` means either the cap has gone back
     to the frozen anchor base of issue #106 -- a linear curve where
     the operator asked for a compounding one -- or it has moved to the
     RAW target and now expands while the cycle spends it, settling at
     ``pct / (1 - pct)`` instead of ``pct``.

THE VACUOUS-PASS CONTROL. A cap that never moves also never moves
wrongly. Every cap assertion here is preceded by an assertion that the
fold actually BOOKED surplus, so a green result cannot come from a fold
that did nothing.

THE TWINS. ``_frozen_cap`` and ``_raw_target_cap`` are the two wrong
answers -- the deleted defect and the tempting repair. Both are driven
beside the shipping property, so an assertion only the property can
satisfy is distinguishable from one all three would pass.

THE LIVE NUMBERS. Every figure marked LIVE was read read-only from
``~/.acervator/bot_state.json`` on 2026-08-26 and is pinned here, so
the arithmetic runs on the operator's own state rather than on a
fixture built to suit the assertion.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading.scrumming_bot import ScrummingBot  # noqa: E402

CHART_SRC = (REPO_ROOT / "src" / "gui" / "widgets" / "trade_charts_tab.py").read_text(
    encoding="utf-8"
)


def _live_settings_source(gui_dir):
    """The Live Bot Settings dialog's whole source: the module and its
    per-tab package, concatenated in a fixed order."""
    parts = [gui_dir / "bot_live_settings.py"]
    parts += sorted((gui_dir / "live_settings").glob("*.py"))
    return "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in parts)


BLS_SRC = _live_settings_source(REPO_ROOT / "src" / "gui")
BC_SRC = (REPO_ROOT / "src" / "trading" / "bot_container.py").read_text(
    encoding="utf-8"
)

# LIVE, CAP/USD, 2026-08-26. The only shape on the fleet that separates
# the three ceiling expressions from each other: the only bot carrying
# BOTH accrued growth and a non-zero in-cycle consumption.
CAP_TARGET = 55.4148
CAP_ANCHOR = 50.00
CAP_CONSUMED = 0.5000
CAP_PCT = 1.0

# LIVE, 2026-08-26. One queued CHIP/USD tranche, and the per-cycle cap
# on BONK/USD, which it does not fit inside.
CHIP_TRANCHE_USD = 16.0523
CHIP_TRANCHE_UNITS = 500.0
CHIP_TRANCHE_REF = 0.03376
BONK_CAP = 1.0103

# The operator's own scrum, issue #133 unit 9: 473 CHIP filled at
# $0.03376 on 2026-08-26.
CHIP_SCRUM_UNITS = 473.0

# The venue's own rate, recorded in ``_settled_sale_proceeds``: 92 of 92
# August 2026 CHIP fills at exactly 1.2000% of subtotal, both sides.
VENUE_FEE = 0.012

# The epsilon `_apply_fold_target_growth` treats as a spent cap.
CAP_SPENT_EPSILON = 1e-9


class _Bus:
    def __init__(self) -> None:
        self.msgs: list[str] = []

    def emit(self, _ev: str, **kw) -> None:
        self.msgs.append(str(kw.get("message", "")))

    def text(self) -> str:
        return "\n".join(self.msgs)


class _Bot:
    """Only the fields the cap, the applier and the preview read.

    Every method is bound off ``ScrummingBot`` itself, so these tests
    drive the shipping code rather than a copy of it.
    """

    cycle_growth_cap_usd = ScrummingBot.cycle_growth_cap_usd
    _apply_fold_target_growth = ScrummingBot._apply_fold_target_growth
    _preview_fold_growth = ScrummingBot._preview_fold_growth
    _plan_fold_consumption = ScrummingBot._plan_fold_consumption
    _settle_fold_plan = ScrummingBot._settle_fold_plan

    def __init__(
        self,
        *,
        anchor=100.0,
        target=None,
        pct=1.0,
        consumed=0.0,
        pool=0.0,
        tranches=None,
        active=True,
        qrate=1.0,
        holdings=1000.0,
    ):
        self.bot_id = "bot-u10"
        self.config = type(
            "C",
            (),
            {"max_target_growth_pct": pct, "profit_folding_active": active},
        )()
        self._bus = _Bus()
        self._quote_to_usd = qrate
        self._anchor_target_balance = anchor
        self._target_balance = anchor if target is None else target
        self._fold_cycle_cap_consumed = consumed
        self._standing_surplus_usd = pool
        self._fold_accumulator = 0.0
        self._target_grow_last_side = None
        self._fold_tranches = list(tranches or [])
        self._current_holdings = holdings
        self.stats = type("S", (), {"standing_surplus_usd": 0.0})()

    def open_next_cycle(self) -> None:
        """What both cycle-reset sites in ``tick`` write.

        ``_fold_cycle_cap_consumed = 0.0`` on a SCRUM fill and on the
        opposite Bollinger extreme. Neither reset touches any other
        field the cap reads.
        """
        self._fold_cycle_cap_consumed = 0.0
        self._target_grow_last_side = None


def _frozen_cap(bot) -> float:
    """THE DELETED DEFECT: the percentage of the frozen anchor."""
    return bot._anchor_target_balance * (bot.config.max_target_growth_pct / 100.0)


def _raw_target_cap(bot) -> float:
    """THE TEMPTING WRONG REPAIR: the percentage of the RAW target.

    It compounds, so it satisfies the headline question. It also grows
    while the cycle spends it.
    """
    return bot._target_balance * (bot.config.max_target_growth_pct / 100.0)


def _tranche(usd, units, ref, ibp=0.02, **extra) -> dict:
    t = {"usd": usd, "units": units, "ref": ref, "initial_buy_price": ibp}
    t.update(extra)
    return t


# -- question 2: the cap steps once per cycle, by the growth ----------


class TestTheCapStepsOncePerCycle:
    def test_a_fold_with_surplus_moves_the_cap_at_the_next_cycle_open(self):
        """The headline. $100 target, 1.0%, $5.00 of fold surplus."""
        b = _Bot(target=100.0, pct=1.0)
        cap_before = b.cycle_growth_cap_usd
        assert cap_before == pytest.approx(1.0)

        growth = b._apply_fold_target_growth(5.0, source="unit10")

        # VACUOUS-PASS CONTROL. Everything below is a statement about a
        # cap that moved because a fold booked surplus.
        assert growth > 0.0, "no surplus was booked; the cap assertions are vacuous"
        assert growth == pytest.approx(1.0)
        assert b._target_balance == pytest.approx(101.0)
        assert b._fold_cycle_cap_consumed == pytest.approx(1.0)
        assert b._standing_surplus_usd == pytest.approx(4.0)

        cap_in_cycle = b.cycle_growth_cap_usd
        assert cap_in_cycle == pytest.approx(cap_before), (
            "the cap moved WHILE the cycle was spending it. The base is "
            "the cycle-open target; a bound that expands as it is "
            "consumed settles at pct/(1-pct), 1.0101% on a 1.0% setting"
        )

        b.open_next_cycle()
        cap_after = b.cycle_growth_cap_usd
        assert cap_after - cap_before == pytest.approx(growth * 1.0 / 100.0), (
            "the cap did not step by the growth this fold applied. A "
            "zero step is issue #106 back: the base returned to "
            "`_anchor_target_balance`, which no Fold ever moves"
        )
        assert cap_after == pytest.approx(1.01)

    def test_DRIVEN_THE_OTHER_WAY_the_two_wrong_twins_behave_differently(self):
        """The check above must be one only the property can satisfy.

        IF THIS FAILS: a twin has stopped being the wrong answer it is
        written to be, and the contrast the headline draws is against
        nothing.
        """
        b = _Bot(target=100.0, pct=1.0)
        frozen_before = _frozen_cap(b)
        raw_before = _raw_target_cap(b)
        growth = b._apply_fold_target_growth(5.0, source="unit10")
        assert growth > 0.0

        # The deleted defect does not move at all, in cycle or across.
        assert _frozen_cap(b) == pytest.approx(frozen_before)
        b.open_next_cycle()
        assert _frozen_cap(b) == pytest.approx(1.0)
        assert b.cycle_growth_cap_usd != pytest.approx(_frozen_cap(b))

        # The tempting repair moves DURING the cycle.
        b2 = _Bot(target=100.0, pct=1.0)
        assert b2._apply_fold_target_growth(5.0, source="unit10") > 0.0
        assert _raw_target_cap(b2) - raw_before == pytest.approx(growth * 0.01)
        assert _raw_target_cap(b2) != pytest.approx(b2.cycle_growth_cap_usd)

    def test_it_compounds_over_ten_cycles_rather_than_adding_linearly(self):
        b = _Bot(target=100.0, pct=1.0)
        caps = []
        for _ in range(10):
            caps.append(b.cycle_growth_cap_usd)
            g = b._apply_fold_target_growth(50.0, source="unit10")
            assert g > 0.0, "vacuous: no surplus booked on this cycle"
            b.open_next_cycle()
        assert b._target_balance == pytest.approx(100.0 * (1.01**10))
        assert caps[0] == pytest.approx(1.0)
        assert caps[-1] == pytest.approx(100.0 * (1.01**9) * 0.01)
        assert b._target_balance > 100.0 + 10 * 1.0, (
            "ten capped folds produced the linear curve anchor x (1 + "
            "0.01N), not anchor x 1.01^N -- issue #106"
        )

    @pytest.mark.parametrize(
        "delta_cents", [-1, 0, 1], ids=["a-cent-under", "exactly-at", "a-cent-over"]
    )
    def test_the_boundary_at_the_cap(self, delta_cents):
        """Surplus a cent under the cap, exactly on it, a cent over."""
        b = _Bot(target=100.0, pct=1.0)
        cap = b.cycle_growth_cap_usd
        offered = cap + delta_cents * 0.01
        growth = b._apply_fold_target_growth(offered, source="unit10")
        assert growth == pytest.approx(min(offered, cap))
        assert b._fold_cycle_cap_consumed == pytest.approx(growth)
        assert b._standing_surplus_usd == pytest.approx(max(0.0, offered - cap))
        b.open_next_cycle()
        assert b.cycle_growth_cap_usd - cap == pytest.approx(growth * 0.01)

    def test_a_second_fold_in_one_cycle_gets_only_the_remainder(self):
        b = _Bot(target=100.0, pct=1.0)
        cap = b.cycle_growth_cap_usd
        first = b._apply_fold_target_growth(0.60, source="unit10")
        assert first == pytest.approx(0.60)
        second = b._apply_fold_target_growth(0.60, source="unit10")
        assert second == pytest.approx(cap - 0.60), (
            "the second fold in one cycle took more than the cap's "
            "remainder, so the per-cycle bound is not cumulative"
        )
        assert b._fold_cycle_cap_consumed == pytest.approx(cap)
        assert b._target_balance == pytest.approx(100.0 + cap)

    def test_a_fold_with_the_cap_spent_parks_the_whole_surplus(self):
        b = _Bot(target=100.0, pct=1.0, consumed=1.0)
        assert b.cycle_growth_cap_usd - b._fold_cycle_cap_consumed <= CAP_SPENT_EPSILON
        growth = b._apply_fold_target_growth(3.0, source="unit10")
        assert growth == 0.0
        assert b._standing_surplus_usd == pytest.approx(3.0)
        assert "TARGET-GROW HELD" in b._bus.text()


# -- question 1: the surplus arithmetic -------------------------------


class TestTheSurplusArithmetic:
    @pytest.mark.parametrize("new_surplus", [0.0, 0.004, 0.5, 1.0, 1.0001, 7.79])
    @pytest.mark.parametrize("pool", [0.0, 0.1563, 7.7922])
    def test_nothing_is_created_or_destroyed(self, new_surplus, pool):
        """applied + pool_after == new_surplus + pool_before.

        IF THIS FAILS: fold profit is appearing in or vanishing from the
        target between the pool and the growth, which is the one thing
        the standing pool exists to make impossible.
        """
        b = _Bot(target=100.0, pct=1.0, pool=pool)
        applied = b._apply_fold_target_growth(new_surplus, source="unit10")
        assert applied + b._standing_surplus_usd == pytest.approx(new_surplus + pool)

    @pytest.mark.parametrize("pool", [0.1563, 7.7922])
    def test_the_pool_is_spendable_and_is_drained_to_the_cap(self, pool):
        """The standing pool is an INPUT to the next fold, not a sink.

        IF THIS FAILS: parked surplus is unreachable, so a bot that
        banked more than one cycle's cap can never spend the remainder.
        """
        b = _Bot(target=100.0, pct=1.0, pool=pool)
        cap = b.cycle_growth_cap_usd
        applied = b._apply_fold_target_growth(0.0, source="unit10")
        assert applied == pytest.approx(min(pool, cap))
        assert b._standing_surplus_usd == pytest.approx(max(0.0, pool - cap))

    def test_the_target_moves_by_exactly_what_was_applied(self):
        b = _Bot(target=CAP_TARGET, anchor=CAP_ANCHOR, pct=CAP_PCT, pool=7.7922)
        before = b._target_balance
        applied = b._apply_fold_target_growth(0.0, source="unit10")
        assert applied > 0.0
        assert b._target_balance - before == pytest.approx(applied)
        assert b._fold_cycle_cap_consumed == pytest.approx(applied)

    def test_the_stats_mirror_carries_the_pool_the_bot_holds(self):
        """The panel reads ``_standing_surplus_usd`` and the status
        export reads the mirror. A mirror that lags shows the operator a
        pool the bot is not holding."""
        b = _Bot(target=100.0, pct=1.0, pool=2.0)
        b._apply_fold_target_growth(0.5, source="unit10")
        assert b.stats.standing_surplus_usd == pytest.approx(b._standing_surplus_usd)

    def test_folding_off_books_no_growth_and_parks_no_surplus(self):
        b = _Bot(target=100.0, pct=1.0, active=False)
        assert b._apply_fold_target_growth(5.0, source="unit10") == 0.0
        assert b._standing_surplus_usd == 0.0
        assert "COMPOUND SKIPPED" in b._bus.text()

    @pytest.mark.parametrize("pct", [0.0, -1.0])
    def test_a_non_positive_rate_is_a_cap_of_zero(self, pct):
        b = _Bot(target=100.0, pct=pct, pool=5.0)
        assert b.cycle_growth_cap_usd == 0.0
        assert b._apply_fold_target_growth(5.0, source="unit10") == 0.0
        assert b._standing_surplus_usd == pytest.approx(10.0)

    def test_a_quote_that_is_not_usd_converts_the_profit_before_the_cap(self):
        """``accum_profit`` arrives pre-conversion. The cap is USD."""
        b = _Bot(target=100.0, pct=1.0, qrate=2.0)
        applied = b._apply_fold_target_growth(0.30, source="unit10")
        assert applied == pytest.approx(0.60)


# -- unit 9b: net proceeds, and what they change ----------------------


def _applier_profit(slices, buy_cost, buy_fill) -> float:
    """The applier's own expression, from the fold-rebuy path.

    ``buy_asset - sum(usd/ref)``, times the fill. Written out because
    the surrounding statements in ``tick`` need a live ticker, a TA
    engine and an exchange to reach.
    """
    buy_asset = buy_cost / buy_fill
    asset_at_scrum = sum(t["usd"] / t["ref"] for t in slices)
    return (buy_asset - asset_at_scrum) * buy_fill


class TestNetProceedsAndTheBookedSurplus:
    @pytest.mark.parametrize("fee", [0.0, VENUE_FEE, 0.016])
    def test_a_rebuy_at_the_scrum_price_books_zero_profit_at_any_fee(self, fee):
        """THE NET/GROSS CONTROL ON THE BOOKED FIGURE.

        A tranche books NET proceeds in ``usd`` and the GROSS fill in
        ``ref``. Both sides of ``buy_asset - sum(usd/ref)`` read the
        same ``usd``, so the fee cancels and a rebuy at the price the
        scrum sold at is worth nothing.

        IF THIS FAILS: the fee is counted on one side only, and every
        fold books a phantom profit or loss equal to it.
        """
        units, ref = CHIP_TRANCHE_UNITS, CHIP_TRANCHE_REF
        net_usd = units * ref * (1.0 - fee)
        slices = [_tranche(net_usd, units, ref)]
        assert _applier_profit(slices, net_usd, ref) == pytest.approx(0.0, abs=1e-9)

    @pytest.mark.parametrize("fee", [0.0, VENUE_FEE, 0.016])
    def test_the_booked_profit_is_the_cash_times_the_price_improvement(self, fee):
        units, ref, price = CHIP_TRANCHE_UNITS, CHIP_TRANCHE_REF, 0.0300
        net_usd = units * ref * (1.0 - fee)
        slices = [_tranche(net_usd, units, ref)]
        got = _applier_profit(slices, net_usd, price)
        assert got == pytest.approx(net_usd * (ref - price) / ref)

    def test_the_preview_overshoots_the_applier_by_exactly_the_fee(self):
        """MEASURED, AND NOT REPAIRED IN THIS UNIT.

        The preview accrues ``take x (ref - price)`` off ``units``. The
        applier accrues the same quantity off ``usd / ref``, and unit 9b
        made ``usd`` net while ``ref`` stayed gross. The ratio is
        ``1 / (1 - fee)``.

        IF THIS FAILS: the preview or the applier changed its profit
        expression, and the two are no longer separated by the fee
        alone.
        """
        units, ref, price = CHIP_SCRUM_UNITS, CHIP_TRANCHE_REF, 0.0300
        net_usd = units * ref * (1.0 - VENUE_FEE)
        buy_units = net_usd / price
        expected_ratio = 1.0 / (1.0 - VENUE_FEE)
        b = _Bot(target=100000.0, pct=100.0, tranches=[_tranche(net_usd, units, ref)])
        applier_usd = _applier_profit([_tranche(net_usd, units, ref)], net_usd, price)
        preview_usd = b._preview_fold_growth(buy_units, price)
        assert applier_usd > 0.0 and preview_usd > 0.0
        ratio = preview_usd / applier_usd
        assert ratio == pytest.approx(expected_ratio, rel=1e-9)
        assert applier_usd == pytest.approx(1.757138, abs=5e-7)
        assert preview_usd == pytest.approx(1.778480, abs=5e-7)
        assert preview_usd - applier_usd == pytest.approx(0.021342, abs=5e-7)

    def test_DRIVEN_THE_OTHER_WAY_a_gross_booked_tranche_shows_no_gap(self):
        """The gap above must be the FEE and not a second difference.

        IF THIS FAILS: the preview and the applier disagree on a
        tranche whose ``usd`` is the gross notional, so something other
        than unit 9b separates them.
        """
        units, ref, price = CHIP_SCRUM_UNITS, CHIP_TRANCHE_REF, 0.0300
        gross_usd = units * ref
        buy_units = gross_usd / price
        b = _Bot(target=100000.0, pct=100.0, tranches=[_tranche(gross_usd, units, ref)])
        applier_usd = _applier_profit(
            [_tranche(gross_usd, units, ref)], gross_usd, price
        )
        preview_usd = b._preview_fold_growth(buy_units, price)
        assert preview_usd == pytest.approx(applier_usd, rel=1e-12)

    def test_the_preview_docstring_states_the_base_it_reads(self):
        """A docstring that states a property is a claim.

        IF THIS FAILS: the preview once again documents a cap taken off
        the ANCHOR while its code reads the cycle-open target.
        """
        doc = " ".join((ScrummingBot._preview_fold_growth.__doc__ or "").split())
        assert "cycle cap off the ANCHOR" not in doc
        assert "cycle-open target and NOT the anchor" in doc
        assert "1 / (1 - venue_fee)" in doc


# -- what is parked, and what is spendable ----------------------------


def _whole_only_plan(eligible, cap_remaining):
    """THE TWIN: admission that refuses to deploy part of a tranche.

    The behaviour the panel and the status export used to describe,
    written out so the assertions below are seen to reject it.
    """
    plan, slices, running = [], [], 0.0
    for t in eligible:
        usd = float(t.get("usd", 0) or 0)
        if running + usd > cap_remaining + 1e-9:
            continue
        plan.append((t, usd, float(t.get("units", 0) or 0)))
        slices.append(dict(t))
        running += usd
    return plan, slices, 0


class TestAnOverCapTrancheIsPartConsumed:
    def test_the_live_chip_tranche_gives_up_the_cap_and_stays_queued(self):
        """LIVE: a $16.0523 tranche against a $1.0103 cycle cap.

        IF THIS FAILS: a tranche larger than one cycle's budget is
        skipped whole, so all five tranches standing on the fleet are
        unspendable for ever and their demarked funds never return.
        """
        t = _tranche(CHIP_TRANCHE_USD, CHIP_TRANCHE_UNITS, CHIP_TRANCHE_REF)
        b = _Bot(tranches=[t])
        plan, slices, partial = b._plan_fold_consumption([t], BONK_CAP)

        assert partial == 1
        assert len(plan) == 1
        assert plan[0][1] == pytest.approx(BONK_CAP)
        assert plan[0][2] == pytest.approx(
            CHIP_TRANCHE_UNITS * BONK_CAP / CHIP_TRANCHE_USD
        )
        assert slices[0]["ref"] == pytest.approx(CHIP_TRANCHE_REF)

        removed, spent = b._settle_fold_plan(plan)
        assert removed == 0 and spent == 0
        assert t["usd"] == pytest.approx(CHIP_TRANCHE_USD - BONK_CAP)
        assert t["units"] == pytest.approx(
            CHIP_TRANCHE_UNITS * (1 - BONK_CAP / CHIP_TRANCHE_USD)
        )
        assert t["fold_partial_spent"] is True
        assert b._fold_tranches == [t]

    def test_DRIVEN_THE_OTHER_WAY_the_whole_only_twin_admits_nothing(self):
        """IF THIS FAILS: the twin is not the refusing behaviour it is
        written to be, so the check above contrasts with nothing."""
        t = _tranche(CHIP_TRANCHE_USD, CHIP_TRANCHE_UNITS, CHIP_TRANCHE_REF)
        plan, slices, partial = _whole_only_plan([t], BONK_CAP)
        assert plan == [] and slices == [] and partial == 0

    def test_the_take_never_exceeds_the_room(self):
        rows = [
            _tranche(16.0523, 500.0, 0.03376),
            _tranche(9.9396, 0.25, 40.0),
            _tranche(6.7095, 300.0, 0.0224),
        ]
        b = _Bot(tranches=list(rows))
        plan, _slices, _partial = b._plan_fold_consumption(rows, 2.6130)
        assert sum(u for _t, u, _x in plan) <= 2.6130 + 1e-9

    def test_a_second_cycle_takes_another_bite_of_the_same_tranche(self):
        """An over-cap tranche is spendable: each cycle takes the cap."""
        t = _tranche(CHIP_TRANCHE_USD, CHIP_TRANCHE_UNITS, CHIP_TRANCHE_REF)
        b = _Bot(tranches=[t])
        for _cycle in range(2):
            plan, _slices, _partial = b._plan_fold_consumption([t], BONK_CAP)
            b._settle_fold_plan(plan)

        assert t["usd"] == pytest.approx(CHIP_TRANCHE_USD - 2 * BONK_CAP)
        assert t["units"] == pytest.approx(
            CHIP_TRANCHE_UNITS * (1 - 2 * BONK_CAP / CHIP_TRANCHE_USD)
        )
        assert b._fold_tranches == [t]

    def test_DRIVEN_THE_OTHER_WAY_the_whole_only_twin_never_takes_a_bite(self):
        """IF THIS FAILS: the twin spends, so the check above proves nothing."""
        t = _tranche(CHIP_TRANCHE_USD, CHIP_TRANCHE_UNITS, CHIP_TRANCHE_REF)
        for _cycle in range(2):
            plan, _slices, _partial = _whole_only_plan([t], BONK_CAP)
            assert plan == []

        assert t["usd"] == pytest.approx(CHIP_TRANCHE_USD)


# -- the chart ceiling, read at the value it draws ---------------------


def _chart_ceiling_segment() -> str:
    """The shipping bytes of the chart's Target-Balance block.

    Sliced out of ``trade_charts_tab.py`` and executed, so this reads
    the
    expression that ships rather than a copy of it.
    """
    i = CHART_SRC.index("anchor_usd = float(")
    i = CHART_SRC.rindex("\n", 0, i) + 1
    j = CHART_SRC.index("set_target_balance_lines(None, None)", i)
    j = CHART_SRC.index("\n", j) + 1
    return textwrap.dedent(CHART_SRC[i:j])


class _Chart:
    def __init__(self):
        self.lines: tuple | None = None

    def set_target_balance_lines(self, anchor_px, ceiling_px):
        self.lines = (anchor_px, ceiling_px)


class _Panel:
    def __init__(self):
        self.chart = _Chart()


def _drawn_lines(bot) -> tuple:
    panel = _Panel()
    exec(  # noqa: S102 - runs this repository's own shipped source
        compile(_chart_ceiling_segment(), "main_window-segment", "exec"),
        {"bot": bot, "panel": panel, "float": float, "getattr": getattr, "max": max},
    )
    lines = panel.chart.lines
    assert lines is not None, "the extracted segment drew no lines at all"
    return lines


class TestTheChartCeilingIsTheEnforcedCeiling:
    def test_the_segment_extracted_is_the_one_that_draws(self):
        """POSITIVE CONTROL ON THE EXTRACTION. A slice that missed the
        arithmetic would run and prove nothing."""
        seg = _chart_ceiling_segment()
        assert "cycle_growth_cap_usd" in seg
        assert "_fold_cycle_cap_consumed" in seg
        assert "set_target_balance_lines" in seg

    def test_on_the_live_CAP_bot_the_line_is_reachable(self):
        """LIVE CAP/USD: target $55.4148, consumed $0.5000, 1.0%.

        IF THIS FAILS: the chart draws a Target-Balance ceiling the bot
        cannot reach this cycle -- a chart and a bot telling the
        operator different stories about the same number.
        """
        b = _Bot(
            target=CAP_TARGET,
            anchor=CAP_ANCHOR,
            pct=CAP_PCT,
            consumed=CAP_CONSUMED,
            holdings=1000.0,
        )
        cap = b.cycle_growth_cap_usd
        assert cap == pytest.approx(0.549148)
        reachable = (b._target_balance - b._fold_cycle_cap_consumed) + cap
        assert reachable == pytest.approx(55.463948)

        anchor_px, ceiling_px = _drawn_lines(b)
        assert anchor_px == pytest.approx(CAP_ANCHOR / 1000.0)
        assert ceiling_px * 1000.0 == pytest.approx(reachable)

    def test_DRIVEN_THE_OTHER_WAY_the_unsubtracted_expression_reads_high(self):
        """IF THIS FAILS: the two expressions agree on a bot with a
        consumed cycle, so the check above cannot tell them apart."""
        b = _Bot(
            target=CAP_TARGET, anchor=CAP_ANCHOR, pct=CAP_PCT, consumed=CAP_CONSUMED
        )
        cap = b.cycle_growth_cap_usd
        unsubtracted = b._target_balance + cap
        reachable = (b._target_balance - b._fold_cycle_cap_consumed) + cap
        assert unsubtracted - reachable == pytest.approx(CAP_CONSUMED)
        assert unsubtracted == pytest.approx(55.963948)

    def test_a_bot_with_nothing_consumed_is_untouched(self):
        """35 of the operator's 38 bots. This must move none of them."""
        b = _Bot(target=63.53, anchor=50.0, pct=1.0, holdings=1000.0)
        _anchor_px, ceiling_px = _drawn_lines(b)
        assert ceiling_px * 1000.0 == pytest.approx(64.1653)

    def test_a_consumption_above_the_target_cannot_invert_the_line(self):
        """Detonation returns the target to the anchor and leaves the
        consumption standing. The floor keeps the ceiling non-negative.
        """
        b = _Bot(target=1.0, anchor=50.0, pct=1.0, consumed=40.0, holdings=1000.0)
        _anchor_px, ceiling_px = _drawn_lines(b)
        assert ceiling_px >= 0.0


# -- the panel figure and the bound are one number --------------------


class TestThePanelReadsWhatTheBotEnforces:
    def test_the_cycle_health_row_reads_the_property_and_the_consumption(self):
        i = BLS_SRC.index("Fold budget this cycle:")
        seg = BLS_SRC[max(0, i - 900) : i]
        assert "cycle_growth_cap_usd" in seg
        assert "_fold_cycle_cap_consumed" in seg

    def test_the_settings_row_reads_the_property_and_the_consumption(self):
        i = BLS_SRC.index("Cycle growth budget:")
        seg = BLS_SRC[max(0, i - 900) : i]
        assert "cycle_growth_cap_usd" in seg
        assert "_fold_cycle_cap_consumed" in seg

    def test_the_status_export_and_the_property_are_one_value(self):
        b = _Bot(
            target=CAP_TARGET, anchor=CAP_ANCHOR, pct=CAP_PCT, consumed=CAP_CONSUMED
        )
        exported = round(float(getattr(b, "cycle_growth_cap_usd", 0.0) or 0.0), 8)
        assert exported == pytest.approx(b.cycle_growth_cap_usd)
        assert exported != pytest.approx(_frozen_cap(b))
        assert exported != pytest.approx(_raw_target_cap(b))
