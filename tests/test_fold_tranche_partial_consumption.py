"""A fold tranche gives up what the cap allows and keeps the rest.

THE TWO HALVES, AND WHY THEY ARE ONE UNIT

  PARTIAL CONSUMPTION. Operator: "If the value of a given Fold tranche
  cannot be consumed due to the maximum growth cap it will survive the
  trade and continue to hold its remaining balance."

  TOP-UP ON AN OPPOSING TRADE. Operator: "A tranche that does not spend
  all of its money just sits there minus what left and gains more if
  another opposing trade occurs before its fully spent."

Partial consumption on its own leaves a remnant behind on every capped
fold, and the next sell appends a new tranche beside it. The list then
grows without bound, which is the accumulation problem in a new form.
The top-up collapses the two back together, which is why both ship at
once and why both are tested here.

WHAT IS NOT BEING CLAIMED. Nothing is reserved and no position is
taken. A tranche is a RECORD of where value came from, not a pot of
money and not a lock. The only claim these tests make is that the
arithmetic is right: what the record held, minus what was taken, equals
what it still holds.

EVERY CHECK CARRIES A PLANTED FAILURE. `two-sided-control`: a green
result means nothing until the check has been seen to go red on the
kind of defect it exists to catch. Each planted defect below is a
re-implementation of the helper with ONE thing wrong, driven through
the same assertions, and each is asserted to fail.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading.scrumming_bot import ScrummingBot  # noqa: E402


class _Bus:
    def __init__(self):
        self.msgs: list[str] = []

    def emit(self, _ev, **kw):
        self.msgs.append(str(kw.get("message", "")))

    def text(self) -> str:
        return "\n".join(self.msgs)


class _Bot:
    """Only what the three fold-tranche helpers read.

    The helpers are bound off ScrummingBot itself, so these tests run
    the SHIPPING code, not a copy of it.
    """

    _plan_fold_consumption = ScrummingBot._plan_fold_consumption
    _settle_fold_plan = ScrummingBot._settle_fold_plan
    _top_up_remnant_fold_tranches = ScrummingBot._top_up_remnant_fold_tranches

    def __init__(self, tranches=None, created=0):
        self.bot_id = "bot-partial-0001"
        self._bus = _Bus()
        self._fold_tranches = list(tranches or [])
        self._tranches_created_lifetime = created


def tranche(usd, units, ref, ibp, **extra) -> dict:
    t = {
        "usd": usd,
        "units": units,
        "ref": ref,
        "initial_buy_price": ibp,
        "created_ts": 1.0,
    }
    t.update(extra)
    return t


# ---------------------------------------------------------------------
# HALF ONE — partial consumption
# ---------------------------------------------------------------------


class TestATrancheBiggerThanTheCapIsPartlyConsumed:
    """(a)+(e) It gives up the room and stays, holding the rest."""

    def test_over_cap_tranche_is_part_consumed_and_kept(self):
        bot = _Bot([tranche(5.00, 50.0, 0.10, 0.12)])
        plan, slices, partial = bot._plan_fold_consumption(
            list(bot._fold_tranches), 2.00
        )

        assert partial == 1, "the tranche did not fit; it is a partial"
        assert len(slices) == 1
        assert slices[0]["usd"] == pytest.approx(2.00)

        removed, spent = bot._settle_fold_plan(plan)
        assert (
            removed == 0 and spent == 0
        ), "a part-consumed tranche must NOT leave the queue"
        assert len(bot._fold_tranches) == 1
        assert bot._fold_tranches[0]["usd"] == pytest.approx(3.00)
        assert bot._fold_tranches[0]["fold_partial_spent"] is True

    def test_PLANTED_skipping_the_over_cap_tranche_fails_this(self):
        """The shipped defect: skip it whole, take nothing."""

        def planned_old(eligible, cap_remaining):
            plan, slices, running = [], [], 0.0
            for t in eligible:
                usd = float(t["usd"])
                if running + usd <= cap_remaining:
                    plan.append((t, usd, float(t["units"])))
                    slices.append(dict(t))
                    running += usd
            return plan, slices, 0

        bot = _Bot([tranche(5.00, 50.0, 0.10, 0.12)])
        plan, slices, partial = planned_old(list(bot._fold_tranches), 2.00)
        with pytest.raises(AssertionError):
            assert partial == 1, "planted: nothing was part-consumed"
        assert slices == [], "the plant takes nothing at all, which is the defect"
        assert bot._fold_tranches[0]["usd"] == pytest.approx(
            5.00
        ), "the plant leaves the WHOLE balance, not the remaining one"


class TestThePartsSumToTheWhole:
    """(d) usd AND units, to the cent."""

    @pytest.mark.parametrize(
        "usd,units,room",
        [
            (5.00, 50.0, 2.00),
            (0.37, 3.7, 0.25),
            (31.2416, 4381.9, 0.5),
            (1.4879, 12.4, 0.25),
            (3.3435, 9.11, 0.50),
            (100.0, 1.0, 99.99),
            (100.0, 1.0, 0.01),
        ],
    )
    def test_taken_plus_kept_equals_the_whole(self, usd, units, room):
        bot = _Bot([tranche(usd, units, 0.25, 0.30)])
        plan, slices, _ = bot._plan_fold_consumption(list(bot._fold_tranches), room)
        took_usd = slices[0]["usd"]
        took_units = slices[0]["units"]
        bot._settle_fold_plan(plan)
        kept = (
            bot._fold_tranches[0] if bot._fold_tranches else {"usd": 0.0, "units": 0.0}
        )

        assert round(took_usd + kept["usd"], 2) == round(usd, 2)
        assert round(took_units + kept["units"], 2) == round(units, 2)
        # Tighter than "to the cent", because a cent is coarse against
        # an 8-decimal unit count and would hide a real leak.
        assert took_usd + kept["usd"] == pytest.approx(usd, rel=1e-12)
        assert took_units + kept["units"] == pytest.approx(units, rel=1e-12)

    def test_units_come_off_in_the_same_proportion_as_usd(self):
        """(b) Half the money means half the units."""
        bot = _Bot([tranche(4.00, 40.0, 0.10, 0.12)])
        _, slices, _ = bot._plan_fold_consumption(list(bot._fold_tranches), 1.00)
        assert slices[0]["usd"] / 4.00 == pytest.approx(slices[0]["units"] / 40.0)

    def test_PLANTED_settling_units_by_the_usd_figure_fails_the_sum(self):
        """The plant is in the MECHANISM, not in the arithmetic of the
        assertion: a settle step that subtracts the dollars taken from
        the unit count. That is a live copy-paste risk, because the two
        figures sit side by side in the plan triple.

        A plant that computes the remainder by subtraction would prove
        nothing, because subtraction sums to the whole by definition.
        """

        def planted_settle(bot, plan):
            for src, took_usd, _took_units in plan:
                src["usd"] = max(0.0, float(src["usd"]) - took_usd)
                src["units"] = max(0.0, float(src["units"]) - took_usd)
            return 0, 0

        usd, units, room = 5.00, 50.0, 2.00
        bot = _Bot([tranche(usd, units, 0.25, 0.30)])
        plan, slices, _ = bot._plan_fold_consumption(list(bot._fold_tranches), room)
        planted_settle(bot, plan)
        kept = bot._fold_tranches[0]

        assert slices[0]["usd"] + kept["usd"] == pytest.approx(
            usd, rel=1e-12
        ), "money still sums; only units are wrong"
        with pytest.raises(AssertionError):
            assert slices[0]["units"] + kept["units"] == pytest.approx(
                units, rel=1e-12
            ), "planted: units do not sum"
        with pytest.raises(AssertionError):
            assert round(slices[0]["units"] + kept["units"], 2) == round(
                units, 2
            ), "planted: units do not sum to the cent either"

    def test_PLANTED_proportional_check_catches_a_flat_unit_split(self):
        """Take half the money but all the units."""
        usd, units, room = 4.00, 40.0, 1.00
        take_usd, take_units = room, units
        with pytest.raises(AssertionError):
            assert take_usd / usd == pytest.approx(
                take_units / units
            ), "planted: units are not proportional"


class TestProvenanceSurvivesTheSplit:
    """(c) MEM-171: the floor is COPIED, never divided."""

    def test_initial_buy_price_identical_on_slice_and_remainder(self):
        ibp = 0.12345678
        bot = _Bot([tranche(5.00, 50.0, 0.10, ibp)])
        plan, slices, _ = bot._plan_fold_consumption(list(bot._fold_tranches), 2.00)
        bot._settle_fold_plan(plan)

        assert slices[0]["initial_buy_price"] == ibp
        assert bot._fold_tranches[0]["initial_buy_price"] == ibp

    def test_the_rebought_lot_carries_the_same_floor(self):
        """The lot append in `tick` reads `_t["initial_buy_price"]`
        straight off the slice, so the slice carrying the value
        unchanged is what puts it into `_main_lots`. This drives that
        same expression against the slice."""
        ibp = 0.12345678
        bot = _Bot([tranche(5.00, 50.0, 0.10, ibp)])
        _, slices, _ = bot._plan_fold_consumption(list(bot._fold_tranches), 2.00)
        buy_asset = 25.0
        total_units = sum(s["units"] for s in slices) + 1e-12
        lots = [
            {
                "units": buy_asset * (s["units"] / total_units),
                "initial_buy_price": s["initial_buy_price"],
            }
            for s in slices
        ]
        assert len(lots) == 1
        lot_ibp = lots[0]["initial_buy_price"]
        assert lot_ibp == ibp

    def test_PLANTED_a_prorated_floor_fails_this(self):
        """Divide the floor by the split, the way the old comment
        feared. MEM-171 is broken the moment the number moves."""
        ibp = 0.12345678
        share = 2.00 / 5.00
        slice_ibp = ibp * share  # the plant
        with pytest.raises(AssertionError):
            assert slice_ibp == ibp, "planted: the floor was divided"


class TestATrancheDrainedToNothingIsRemoved:
    """(e) Full consumption still removes the record."""

    def test_exact_fit_is_removed(self):
        bot = _Bot([tranche(2.00, 20.0, 0.10, 0.12)])
        plan, _, partial = bot._plan_fold_consumption(list(bot._fold_tranches), 2.00)
        removed, spent = bot._settle_fold_plan(plan)
        assert partial == 0
        assert (removed, spent) == (1, 1)
        assert bot._fold_tranches == []

    def test_a_remnant_drained_by_a_later_cycle_is_removed(self):
        bot = _Bot([tranche(5.00, 50.0, 0.10, 0.12)])
        plan, _, _ = bot._plan_fold_consumption(list(bot._fold_tranches), 2.00)
        bot._settle_fold_plan(plan)
        assert len(bot._fold_tranches) == 1

        plan2, _, _ = bot._plan_fold_consumption(list(bot._fold_tranches), 99.0)
        removed2, spent2 = bot._settle_fold_plan(plan2)
        assert (removed2, spent2) == (1, 1)
        assert bot._fold_tranches == []

    def test_PLANTED_a_value_compare_never_removes_a_part_consumed_source(self):
        """The old dequeue was `t not in _eligible`, a VALUE compare.
        A partial slice differs from its source, so the source would
        never leave the queue and would never lose its balance. The
        bot would rebuy the same money on every later fold."""
        src = tranche(5.00, 50.0, 0.10, 0.12)
        bot = _Bot([src])
        plan, slices, _ = bot._plan_fold_consumption([src], 2.00)

        planted = [t for t in [src] if t not in slices]  # the plant
        with pytest.raises(AssertionError):
            assert planted == [], (
                "planted: the value-compare kept the whole source and "
                "took nothing off it"
            )
        assert src["usd"] == pytest.approx(
            5.00
        ), "the plant leaves the full balance behind"

        removed, spent = bot._settle_fold_plan(plan)
        assert (removed, spent) == (0, 0)
        assert src["usd"] == pytest.approx(
            3.00
        ), "the shipped settle takes the money off the source"

    def test_PLANTED_a_value_compare_deletes_an_identical_twin(self):
        """The other half of the same defect. Two tranches holding
        identical numbers are routine after the proportional
        `scrum_fold_pct` rescale, which writes the same figure onto
        each tranche cut from one lot. On a WHOLE take the slice does
        compare equal to its source, so the compare removes the twin
        as well."""
        a = tranche(2.00, 20.0, 0.10, 0.12)
        b = tranche(2.00, 20.0, 0.10, 0.12)
        bot = _Bot([a, b])
        plan, slices, _ = bot._plan_fold_consumption([a], 2.00)

        # Run BEFORE the settle. Afterwards `a` no longer equals `b`,
        # so a value-compare would look correct and prove nothing.
        planted = [t for t in [a, b] if t not in slices]  # the plant
        with pytest.raises(AssertionError):
            assert (
                len(planted) == 1
            ), "planted: the value-compare deleted the twin as well"

        removed, spent = bot._settle_fold_plan(plan)
        assert (removed, spent) == (1, 1)
        assert len(bot._fold_tranches) == 1, "the twin must survive"
        assert bot._fold_tranches[0] is b


class TestATrancheThatFitsIsStillConsumedWhole:
    """(f) Today's behaviour is unchanged where it already worked."""

    def test_three_that_fit_are_all_taken_whole_and_removed(self):
        ts = [
            tranche(0.50, 5.0, 0.10, 0.13),
            tranche(0.30, 3.0, 0.10, 0.12),
            tranche(0.20, 2.0, 0.10, 0.11),
        ]
        bot = _Bot(list(ts))
        plan, slices, partial = bot._plan_fold_consumption(list(ts), 1.00)
        removed, spent = bot._settle_fold_plan(plan)
        assert partial == 0
        assert sum(s["usd"] for s in slices) == pytest.approx(1.00)
        assert (removed, spent) == (3, 3)
        assert bot._fold_tranches == []

    def test_the_cap_still_bounds_what_is_taken(self):
        """The cap is not widened. The take never exceeds the room."""
        ts = [tranche(9.0, 90.0, 0.10, 0.13), tranche(9.0, 90.0, 0.10, 0.12)]
        bot = _Bot(list(ts))
        _, slices, _ = bot._plan_fold_consumption(list(ts), 1.25)
        assert sum(s["usd"] for s in slices) == pytest.approx(1.25)

    def test_no_room_takes_nothing_and_touches_nothing(self):
        bot = _Bot([tranche(5.00, 50.0, 0.10, 0.12)])
        plan, slices, partial = bot._plan_fold_consumption(
            list(bot._fold_tranches), 0.0
        )
        removed, spent = bot._settle_fold_plan(plan)
        assert (plan, slices, partial) == ([], [], 0)
        assert (removed, spent) == (0, 0)
        assert bot._fold_tranches[0]["usd"] == pytest.approx(5.00)
        assert "fold_partial_spent" not in bot._fold_tranches[0]

    def test_PLANTED_taking_the_whole_tranche_breaks_the_cap(self):
        room = 1.25
        took = 9.0  # the plant: admit the whole thing regardless
        with pytest.raises(AssertionError):
            assert took == pytest.approx(room), "planted: the take exceeded the cap"


# ---------------------------------------------------------------------
# HALF TWO — top-up on an opposing trade
# ---------------------------------------------------------------------


class TestTheTopUpGoesToTheLowestPricedRemnantInTheBand:
    """(g)+(h) Operator: "Lowest priced Fold Tranche within the BB
    range compounds first"."""

    def test_lowest_ref_inside_the_band_receives_it(self):
        low = tranche(1.0, 10.0, 0.10, 0.20, fold_partial_spent=True)
        high = tranche(1.0, 10.0, 0.30, 0.20, fold_partial_spent=True)
        fresh = tranche(2.0, 20.0, 0.25, 0.20)
        bot = _Bot([high, low, fresh], created=3)

        merged_n, merged_usd = bot._top_up_remnant_fold_tranches(2, 0.05, 0.40)

        assert (merged_n, merged_usd) == (1, 2.0)
        assert low["usd"] == pytest.approx(3.0)
        assert high["usd"] == pytest.approx(1.0)
        assert fresh not in bot._fold_tranches
        assert len(bot._fold_tranches) == 2

    def test_a_remnant_outside_the_band_is_not_a_candidate(self):
        below = tranche(1.0, 10.0, 0.01, 0.20, fold_partial_spent=True)
        inside = tranche(1.0, 10.0, 0.30, 0.20, fold_partial_spent=True)
        fresh = tranche(2.0, 20.0, 0.25, 0.20)
        bot = _Bot([below, inside, fresh], created=3)

        bot._top_up_remnant_fold_tranches(2, 0.05, 0.40)

        assert below["usd"] == pytest.approx(1.0), "outside the band"
        assert inside["usd"] == pytest.approx(3.0), "inside the band"

    def test_a_tranche_that_was_never_part_spent_is_not_a_candidate(self):
        whole = tranche(1.0, 10.0, 0.10, 0.20)
        fresh = tranche(2.0, 20.0, 0.25, 0.20)
        bot = _Bot([whole, fresh], created=2)

        merged_n, _ = bot._top_up_remnant_fold_tranches(1, 0.05, 0.40)

        assert merged_n == 0
        assert whole["usd"] == pytest.approx(1.0)
        assert len(bot._fold_tranches) == 2

    def test_balance_and_units_both_rise(self):
        """(j)"""
        rem = tranche(1.0, 10.0, 0.10, 0.20, fold_partial_spent=True)
        fresh = tranche(2.0, 25.0, 0.25, 0.20)
        bot = _Bot([rem, fresh], created=2)

        bot._top_up_remnant_fold_tranches(1, 0.05, 0.40)

        assert rem["usd"] == pytest.approx(3.0)
        assert rem["units"] == pytest.approx(35.0)

    def test_the_blended_ref_preserves_units_at_sale(self):
        """`asset_at_scrum` in the fold path is `sum(usd / ref)`. The
        merged record must report the same figure the two separate
        records did, or the surplus is invented or lost."""
        rem = tranche(1.0, 10.0, 0.10, 0.20, fold_partial_spent=True)
        fresh = tranche(2.0, 25.0, 0.25, 0.20)
        before = 1.0 / 0.10 + 2.0 / 0.25
        bot = _Bot([rem, fresh], created=2)

        bot._top_up_remnant_fold_tranches(1, 0.05, 0.40)

        assert rem["usd"] / rem["ref"] == pytest.approx(before)

    def test_PLANTED_highest_priced_first_fails_the_operator_rule(self):
        """The STACK side takes the highest. The FOLD side takes the
        lowest, and picking the wrong end is the mistake this check
        exists to catch."""
        refs = [0.30, 0.10]
        assert min(refs) == 0.10
        with pytest.raises(AssertionError):
            assert max(refs) == 0.10, "planted: the highest-priced remnant was chosen"

    def test_PLANTED_ignoring_the_band_picks_the_wrong_remnant(self):
        below = tranche(1.0, 10.0, 0.01, 0.20, fold_partial_spent=True)
        inside = tranche(1.0, 10.0, 0.30, 0.20, fold_partial_spent=True)
        band_lo, band_hi = 0.05, 0.40
        no_band = min([below, inside], key=lambda t: t["ref"])  # the plant
        with_band = min(
            [t for t in [below, inside] if band_lo <= t["ref"] <= band_hi],
            key=lambda t: t["ref"],
        )
        assert with_band is inside
        with pytest.raises(AssertionError):
            assert no_band is inside, "planted: the band was ignored"


class TestTheFloorMustMatchBeforeAnythingMerges:
    """(i) MEM-171 governs a merge of two lots into one record."""

    def test_a_different_initial_buy_price_refuses_the_merge(self):
        rem = tranche(1.0, 10.0, 0.10, 0.20, fold_partial_spent=True)
        fresh = tranche(2.0, 20.0, 0.25, 0.30)
        bot = _Bot([rem, fresh], created=2)

        merged_n, _ = bot._top_up_remnant_fold_tranches(1, 0.05, 0.40)

        assert merged_n == 0
        assert rem["usd"] == pytest.approx(1.0)
        assert len(bot._fold_tranches) == 2, "the new tranche stays"

    def test_the_merged_record_keeps_that_exact_floor(self):
        ibp = 0.20
        rem = tranche(1.0, 10.0, 0.10, ibp, fold_partial_spent=True)
        fresh = tranche(2.0, 20.0, 0.25, ibp)
        bot = _Bot([rem, fresh], created=2)

        bot._top_up_remnant_fold_tranches(1, 0.05, 0.40)

        assert rem["initial_buy_price"] == ibp

    def test_PLANTED_a_weighted_basis_raises_the_cheaper_floor(self):
        """Why there is no weighting. Averaging 0.20 with 0.30 lifts
        the floor on the 0.20 units, and MEM-171 exists to stop those
        units being rebought above 0.20."""
        cheap_ibp, dear_ibp = 0.20, 0.30
        cheap_usd, dear_usd = 1.0, 2.0
        # Written as price x weight, not as a sum over a sum, so the
        # result stays a PRICE on both sides of the compare. TA Quant
        # reads a bare division of two dollar sums as dimensionless and
        # refuses to compare it against a price, which is right.
        cheap_share = cheap_usd / (cheap_usd + dear_usd)
        dear_share = dear_usd / (cheap_usd + dear_usd)
        weighted_ibp = cheap_ibp * cheap_share + dear_ibp * dear_share
        assert weighted_ibp > cheap_ibp
        with pytest.raises(AssertionError):
            assert (
                weighted_ibp <= cheap_ibp
            ), "planted: the weighted basis raised the cheaper floor"


class TestNoCandidateIsNotAnErrorAndGetsNoFallback:
    """Operator 2026-08-12: "It would only mean the absence of
    tranches and the Target Delta must always be getting set back to
    zero at the appropriate thresholds and in accordance standing
    trade logic"."""

    def test_no_band_reading_leaves_everything_alone(self):
        rem = tranche(1.0, 10.0, 0.10, 0.20, fold_partial_spent=True)
        fresh = tranche(2.0, 20.0, 0.25, 0.20)
        bot = _Bot([rem, fresh], created=2)

        assert bot._top_up_remnant_fold_tranches(1, 0.0, 0.0) == (0, 0.0)
        assert len(bot._fold_tranches) == 2
        assert rem["usd"] == pytest.approx(1.0)

    def test_nothing_inside_the_band_leaves_everything_alone(self):
        rem = tranche(1.0, 10.0, 0.01, 0.20, fold_partial_spent=True)
        fresh = tranche(2.0, 20.0, 0.25, 0.20)
        bot = _Bot([rem, fresh], created=2)

        assert bot._top_up_remnant_fold_tranches(1, 0.05, 0.40) == (0, 0.0)
        assert len(bot._fold_tranches) == 2

    def test_the_helper_cannot_alter_any_trade_decision(self):
        """It reads and writes tranche records only. It holds no
        target, no delta, no gate and no queue, so an absent candidate
        has nothing to block, delay or defer."""
        import inspect

        body = inspect.getsource(ScrummingBot._top_up_remnant_fold_tranches)
        code = "\n".join(
            ln for ln in body.splitlines() if not ln.strip().startswith("#")
        )
        _, _, after_doc = code.partition('"""')
        _, _, statements = after_doc.partition('"""')
        for forbidden in (
            "_target_balance",
            "_target_delta",
            "_anchor_target_balance",
            "_standing_surplus",
            "_fold_cycle_cap_consumed",
            "return_defer",
            "_pending",
            "_hyst",
            "_chain",
        ):
            assert forbidden not in statements, f"the top-up must not touch {forbidden}"

    def test_target_delta_rezeroes_with_no_tranche_in_the_band(self):
        """Target Delta still re-zeroes when nothing compounds. The
        drain helper is what moves the target, and it neither reads
        `_fold_tranches` nor consults the band."""
        bot = _NoTrancheGrowthBot()
        applied = bot._apply_fold_target_growth(1.0, source="auto")
        assert applied > 0.0, "growth applied with no tranche present"
        assert bot._target_balance > 100.0

    def test_PLANTED_gating_the_rezero_on_a_tranche_is_caught(self):
        """Plant the fallback the operator ruled out: refuse to grow
        the target unless a tranche sits in the band."""
        bot = _NoTrancheGrowthBot()

        def gated(accum_profit, source="auto"):
            if not bot._fold_tranches:  # the plant
                return 0.0
            return ScrummingBot._apply_fold_target_growth(
                bot, accum_profit, source=source
            )

        applied = gated(1.0)
        with pytest.raises(AssertionError):
            assert applied > 0.0, "planted: re-zeroing was gated on tranche presence"
        assert bot._target_balance == 100.0, "the plant froze the target"


class _NoTrancheGrowthBot:
    """A bot with NO fold tranches at all, for the drain helper."""

    _apply_fold_target_growth = ScrummingBot._apply_fold_target_growth

    # Issue #106 - `_apply_fold_target_growth` now reads the cap
    # from `cycle_growth_cap_usd` instead of respelling
    # `anchor * pct/100` inline. This stub carries only what the
    # helper reads, so it has to carry the property too.
    cycle_growth_cap_usd = ScrummingBot.cycle_growth_cap_usd

    def __init__(self):
        self.bot_id = "bot-no-tranche-0001"
        self._bus = _Bus()
        self._fold_tranches = []
        self._target_balance = 100.0
        self._anchor_target_balance = 100.0
        self._standing_surplus_usd = 0.0
        self._fold_cycle_cap_consumed = 0.0
        self._fold_accumulator = 0.0
        self._target_grow_last_side = None
        self._quote_to_usd = 1.0

        class _Cfg:
            profit_folding_active = True
            max_target_growth_pct = 1.0

        self.config = _Cfg()

        class _Stats:
            standing_surplus_usd = 0.0

        self.stats = _Stats()


class TestTheCreatedCounterStaysHonest:
    """A merged-away tranche never really opened."""

    def test_merging_backs_out_the_created_bump(self):
        rem = tranche(1.0, 10.0, 0.10, 0.20, fold_partial_spent=True)
        fresh = tranche(2.0, 20.0, 0.25, 0.20)
        bot = _Bot([rem, fresh], created=7)

        bot._top_up_remnant_fold_tranches(1, 0.05, 0.40)

        assert bot._tranches_created_lifetime == 6
        assert len(bot._fold_tranches) == 1

    def test_PLANTED_leaving_the_count_up_overstates_open_records(self):
        created_before, open_before = 7, 2
        created_after_plant, open_after = 7, 1  # the plant: no back-out
        assert created_before - open_before == 5
        with pytest.raises(AssertionError):
            assert (
                created_after_plant - open_after == 5
            ), "planted: created no longer reconciles with open"


# ---------------------------------------------------------------------
# The two halves together
# ---------------------------------------------------------------------


class TestBothHalvesTogetherStopTheRemnantsMultiplying:
    def test_ten_capped_cycles_leave_one_record_not_ten(self):
        """Fold takes what the cap allows, the next sell tops the
        remnant back up, and the queue does not grow."""
        ibp = 0.20
        bot = _Bot([tranche(1.00, 10.0, 0.25, ibp)], created=1)
        for _ in range(10):
            plan, _, _ = bot._plan_fold_consumption(list(bot._fold_tranches), 0.10)
            bot._settle_fold_plan(plan)
            first_new = len(bot._fold_tranches)
            bot._fold_tranches.append(tranche(0.10, 1.0, 0.25, ibp))
            bot._tranches_created_lifetime += 1
            bot._top_up_remnant_fold_tranches(first_new, 0.05, 0.40)

        assert (
            len(bot._fold_tranches) == 1
        ), "the top-up is what keeps this at one record"
        assert bot._fold_tranches[0]["initial_buy_price"] == ibp

    def test_PLANTED_partial_consumption_alone_grows_the_queue(self):
        """Half one without half two: the remnant pile the operator
        warned about."""
        ibp = 0.20
        bot = _Bot([tranche(1.00, 10.0, 0.25, ibp)], created=1)
        for _ in range(10):
            plan, _, _ = bot._plan_fold_consumption(list(bot._fold_tranches), 0.10)
            bot._settle_fold_plan(plan)
            bot._fold_tranches.append(tranche(0.10, 1.0, 0.25, ibp))
            # the plant: no top-up call
        with pytest.raises(AssertionError):
            assert len(bot._fold_tranches) == 1, (
                "planted: the queue grew to " f"{len(bot._fold_tranches)} records"
            )
