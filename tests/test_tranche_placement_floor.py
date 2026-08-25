"""Tranche placement has a floor -- GitHub issue #133, Unit 5.

OPERATOR DIRECTIVE 2026-08-25
    "Tranche placement should be greater than or equal to Minimum
     Opposing Trade Distance + Trading Fee. It will be greater if the
     opposing bollinger band is further away but it cannot be less."

WHAT "MINIMUM OPPOSING TRADE DISTANCE + TRADING FEE" IS CALLED HERE.
`otd_math.minimum_opposing_trade_distance_pct(interval, fee)`, which is
`scrumming_interval_pct + trading_fee_pct` clamped to [0, 50]. The fee
is already inside that number. Every floor in this file is read from
that function, never written as a literal, so a test cannot agree with
`stack_math` by both quoting the same constant.

WHERE PLACEMENT IS DECIDED. `stack_math._ladder_prices`, reached from
`scrum_ladder_prices`, `fold_ladder_prices` and
`split_scrum_into_tranches`. Its own docstring: "WHAT THIS MODULE
DECIDES: where a rung sits. That is all."

THE CASE THE FIX EXISTS FOR. The ladder anchor is offset from `base`,
and for the fibonacci mode `base` is the LAST CANDLE CLOSE, not the
price that fired the scrum. A scrum firing on a spike above the close
therefore built its sell ladder off a lower number. Measured over the
38 live bot configs, 38 of 304 (config x mode x side) placements landed
under the bot's own floor; the worst put level 1 2.2827% above the
trigger against a 6.6000% floor, and a close 10% under the trigger put
a SELL rung 3.101% BELOW the price that fired the scrum.

THE CONTROL THAT MATTERS MOST. A fix that always returned the floor
would also never return less than the floor, and would pass every
floor-only test in this file while destroying the spacing law. Class
`TestTheFixDoesNotClampEverythingToTheFloor` is that control, and
`test_PLANT_a_fix_that_always_returns_the_floor_goes_red` proves the
control can fail.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from src.trading.otd_math import minimum_opposing_trade_distance_pct
from src.trading.stack_math import (
    SPACING_MODES,
    fold_ladder_prices,
    level_multipliers,
    placement_floor_price,
    scrum_ladder_prices,
    split_scrum_into_tranches,
)

# The live fleet as captured for issue #97, committed beside this file.
# Read-only; the operator's runtime tree is never touched by the suite.
FLEET = json.loads(
    (
        pathlib.Path(__file__).parent / "data_fold_price_gate_fleet_2026_08_23.json"
    ).read_text(encoding="utf-8")
)

TRIGGER = 100.0
GAP = 1.0  # `split_distance` is 1.0 on all 38 live bots
LEVELS = 3
# 100.0 * (1 + 6.6/100) reads back as 6.600000000000009 percent, so a
# bare `>` cannot tell "further out" from "clamped onto the floor".
EPS = 1e-6


def fleet_floor_pcts() -> list[float]:
    """Every distinct MOTD+fee across the 38 live bot configs."""
    return sorted(
        {
            minimum_opposing_trade_distance_pct(
                b["scrumming_interval_pct"], b["trading_fee_pct"]
            )
            for b in FLEET["bots"]
        }
    )


def placement_pct(direction: int, level_one: float, trigger: float = TRIGGER) -> float:
    """Level 1's distance from the TRIGGER price, in percent."""
    return direction * (level_one / trigger - 1.0) * 100.0


def reference_level_one(
    direction: int,
    trigger: float,
    gap_pct: float,
    mode: str,
    otd_pct: float,
    close: float | None = None,
) -> float:
    """A second witness, written from the spacing law rather than read
    off `stack_math`: anchor at the MOTD, level 1 one initial gap
    beyond it, and the whole ladder lifted if level 1 falls short of
    max(MOTD, opposing band). No band here -- band cases assert against
    the band price itself, which is a third independent value.
    """
    base = close if mode == "fibonacci" else trigger
    anchor = base * (1.0 + direction * otd_pct / 100.0)
    mult = level_multipliers(mode, 1)[0]
    p1 = anchor * (1.0 + direction * mult * gap_pct / 100.0)
    floor = trigger * (1.0 + direction * otd_pct / 100.0)
    if otd_pct > 0 and direction * (floor - p1) > 0:
        return floor
    return p1


# ---------------------------------------------------------------------------
# The floor is enforced at the placement site
# ---------------------------------------------------------------------------


class TestPlacementNeverSitsUnderTheFloor:
    FLOOR = minimum_opposing_trade_distance_pct(5.0, 1.6)  # 6.6 -- 24 live bots

    def test_the_floor_is_the_otd_math_sum_not_a_literal(self):
        """A failure means this file and `stack_math` could agree by
        quoting one constant instead of by computing the same rule."""
        assert self.FLOOR == pytest.approx(6.6, rel=1e-12)
        assert self.FLOOR in fleet_floor_pcts()

    def test_the_pre_fix_arithmetic_really_did_land_under_the_floor(self):
        """A failure means the defect this unit repairs was never
        reachable, and the repair is answering nothing."""
        close = TRIGGER * 0.95
        anchor = close * (1.0 + self.FLOOR / 100.0)
        pre_fix_level_one = anchor * (1.0 + GAP / 100.0)
        assert placement_pct(+1, pre_fix_level_one) == pytest.approx(2.2827, abs=1e-4)
        assert placement_pct(+1, pre_fix_level_one) < self.FLOOR

    def test_a_close_below_the_trigger_used_to_price_a_sell_rung_under_it(self):
        """A failure means the worst pre-fix case -- a sell tranche
        priced below the price that fired the scrum -- was imaginary."""
        close = TRIGGER * 0.90
        pre_fix_level_one = close * (1.0 + self.FLOOR / 100.0) * (1.0 + GAP / 100.0)
        assert pre_fix_level_one < TRIGGER
        assert placement_pct(+1, pre_fix_level_one) == pytest.approx(-3.101, abs=1e-3)

    @pytest.mark.parametrize("close_mult", [0.99, 0.95, 0.90, 0.80])
    def test_the_scrum_side_now_sits_exactly_on_the_floor(self, close_mult):
        """A failure means a fibonacci sell ladder can still be placed
        nearer the trigger than its own round trip costs."""
        prices = scrum_ladder_prices(
            TRIGGER,
            LEVELS,
            GAP,
            "fibonacci",
            min_opposing_pct=self.FLOOR,
            last_candle_close=TRIGGER * close_mult,
        )
        assert placement_pct(+1, prices[0]) == pytest.approx(self.FLOOR, rel=1e-12)
        assert prices[0] == pytest.approx(
            reference_level_one(
                +1, TRIGGER, GAP, "fibonacci", self.FLOOR, TRIGGER * close_mult
            ),
            rel=1e-12,
        )

    @pytest.mark.parametrize("close_mult", [1.011, 1.05, 1.10, 1.20])
    def test_the_fold_side_mirrors_it(self, close_mult):
        """A failure means the two sides of the ladder disagree about
        the floor, which is the drift `stack_math` exists to prevent."""
        prices = fold_ladder_prices(
            TRIGGER,
            LEVELS,
            GAP,
            "fibonacci",
            min_opposing_pct=self.FLOOR,
            last_candle_close=TRIGGER * close_mult,
        )
        assert placement_pct(-1, prices[0]) == pytest.approx(self.FLOOR, rel=1e-12)
        assert prices[0] == pytest.approx(
            reference_level_one(
                -1, TRIGGER, GAP, "fibonacci", self.FLOOR, TRIGGER * close_mult
            ),
            rel=1e-12,
        )

    def test_the_floor_reaches_the_surface_the_scrum_path_consumes(self):
        """A failure means the tranche builder can still ship a rung the
        ladder function would have refused."""
        tranches = split_scrum_into_tranches(
            scrum_price=TRIGGER,
            scrum_size=9.0,
            n_target=LEVELS,
            split_distance_pct=GAP,
            spacing_mode="fibonacci",
            min_opposing_pct=self.FLOOR,
            last_candle_close=TRIGGER * 0.90,
        )
        assert placement_pct(+1, tranches[0].price) == pytest.approx(
            self.FLOOR, rel=1e-12
        )

    def test_a_lifted_ladder_keeps_its_price_order(self):
        """A failure means the lift reordered the rungs, and the merge
        and min-order-size steps downstream read a scrambled ladder."""
        up = scrum_ladder_prices(
            TRIGGER,
            6,
            GAP,
            "fibonacci",
            min_opposing_pct=self.FLOOR,
            last_candle_close=TRIGGER * 0.80,
        )
        down = fold_ladder_prices(
            TRIGGER,
            6,
            GAP,
            "fibonacci",
            min_opposing_pct=self.FLOOR,
            last_candle_close=TRIGGER * 1.20,
        )
        assert up == sorted(up) and len(set(up)) == 6
        assert down == sorted(down, reverse=True) and len(set(down)) == 6
        assert min(down) > 0.0

    def test_a_fold_floor_that_is_not_a_price_is_refused(self):
        """A failure means a >=100% fold floor returns a zero or
        negative price instead of raising."""
        with pytest.raises(ValueError):
            fold_ladder_prices(
                TRIGGER,
                1,
                GAP,
                "fibonacci",
                min_opposing_pct=100.0,
                last_candle_close=TRIGGER * 2.0,
            )


# ---------------------------------------------------------------------------
# The opposing band raises the floor. It never lowers it.
# ---------------------------------------------------------------------------


class TestTheOpposingBandCanOnlyRaisePlacement:
    FLOOR = minimum_opposing_trade_distance_pct(5.0, 1.6)  # 6.6

    def test_a_band_further_out_than_the_floor_sets_the_placement(self):
        """A failure means the fix clamps to the floor and ignores a
        band the operator said should push placement further out."""
        upper = TRIGGER * 1.12  # 12% away, further than the 6.6% floor
        prices = scrum_ladder_prices(
            TRIGGER,
            LEVELS,
            GAP,
            "fibonacci",
            min_opposing_pct=self.FLOOR,
            last_candle_close=TRIGGER * 0.90,
            bb_bounds=(TRIGGER * 0.90, upper),
        )
        assert prices[0] == pytest.approx(upper, rel=1e-12)
        assert placement_pct(+1, prices[0]) > self.FLOOR + EPS

    def test_the_fold_side_takes_the_lower_band(self):
        """A failure means the ladder read the wrong edge, and a buy
        ladder was placed against the sell-side band."""
        lower = TRIGGER * 0.88
        prices = fold_ladder_prices(
            TRIGGER,
            LEVELS,
            GAP,
            "fibonacci",
            min_opposing_pct=self.FLOOR,
            last_candle_close=TRIGGER * 1.10,
            bb_bounds=(lower, TRIGGER * 1.10),
        )
        assert prices[0] == pytest.approx(lower, rel=1e-12)

    def test_a_band_nearer_than_the_floor_does_not_lower_placement(self):
        """A failure means a tight band pulled placement back inside a
        round trip it cannot clear."""
        prices = scrum_ladder_prices(
            TRIGGER,
            LEVELS,
            GAP,
            "fibonacci",
            min_opposing_pct=self.FLOOR,
            last_candle_close=TRIGGER * 0.90,
            bb_bounds=(TRIGGER * 0.99, TRIGGER * 1.01),
        )
        assert placement_pct(+1, prices[0]) == pytest.approx(self.FLOOR, rel=1e-12)

    def test_a_band_nearer_than_the_floor_does_not_refuse_the_ladder(self):
        """A failure means the band vetoes the floor -- the band
        lowering placement to nothing at all."""
        prices = scrum_ladder_prices(
            TRIGGER,
            LEVELS,
            GAP,
            "quadratic",
            min_opposing_pct=self.FLOOR,
            bb_bounds=(TRIGGER * 0.99, TRIGGER * 1.01),
        )
        assert placement_pct(+1, prices[0]) >= self.FLOOR

    def test_the_band_still_refuses_an_over_wide_initial_gap(self):
        """A failure means the operator's older BB rule was retired
        rather than out-ranked in the one case that conflicts."""
        with pytest.raises(ValueError, match="outside the local BB range"):
            scrum_ladder_prices(
                TRIGGER, LEVELS, 5.0, "quadratic", bb_bounds=(99.0, 101.0)
            )

    def test_the_helper_reports_which_value_won(self):
        """A failure means `max(floor, band)` is not what the placement
        site computes, so the rule cannot be read off one function."""
        near = (TRIGGER * 0.99, TRIGGER * 1.01)
        far = (TRIGGER * 0.88, TRIGGER * 1.12)
        assert placement_floor_price(+1, TRIGGER, self.FLOOR, near) == pytest.approx(
            TRIGGER * (1.0 + self.FLOOR / 100.0), rel=1e-12
        )
        assert placement_floor_price(+1, TRIGGER, self.FLOOR, far) == pytest.approx(
            far[1], rel=1e-12
        )
        assert placement_floor_price(-1, TRIGGER, self.FLOOR, far) == pytest.approx(
            far[0], rel=1e-12
        )
        assert placement_floor_price(+1, TRIGGER, 0.0, far) is None


# ---------------------------------------------------------------------------
# THE VACUOUS-PASS CONTROL
# ---------------------------------------------------------------------------


class TestTheFixDoesNotClampEverythingToTheFloor:
    """A change that always returned the floor would satisfy "never less
    than the floor" and destroy the spacing law. These fail on it.
    """

    FLOOR = minimum_opposing_trade_distance_pct(5.0, 1.6)  # 6.6

    @pytest.mark.parametrize("mode", ["quadratic", "linear", "exponential"])
    def test_a_ladder_that_already_clears_the_floor_is_not_moved(self, mode):
        """A failure means the fix rewrote placements that were already
        legal, and every non-fibonacci ladder shifted."""
        prices = scrum_ladder_prices(
            TRIGGER, LEVELS, GAP, mode, min_opposing_pct=self.FLOOR
        )
        assert prices[0] == pytest.approx(
            reference_level_one(+1, TRIGGER, GAP, mode, self.FLOOR), rel=1e-12
        )
        assert placement_pct(+1, prices[0]) > self.FLOOR + EPS

    def test_level_one_stays_one_initial_gap_beyond_the_anchor(self):
        """A failure means the spacing law lost its level-1 row: the
        operator's table starts at exactly one initial gap."""
        anchor = TRIGGER * (1.0 + self.FLOOR / 100.0)
        prices = scrum_ladder_prices(
            TRIGGER, 7, GAP, "quadratic", min_opposing_pct=self.FLOOR
        )
        assert prices[0] == pytest.approx(anchor * (1.0 + GAP / 100.0), rel=1e-12)
        assert prices[3] == pytest.approx(anchor * (1.0 + 16.0 / 100.0), rel=1e-12)

    @pytest.mark.parametrize("close_mult", [0.999, 1.0, 1.05])
    def test_a_close_that_already_clears_the_floor_is_not_lifted(self, close_mult):
        """A failure means the lift fires on ladders that were already
        legal -- the floor binds only below close/trigger = 0.990099."""
        prices = scrum_ladder_prices(
            TRIGGER,
            LEVELS,
            GAP,
            "fibonacci",
            min_opposing_pct=self.FLOOR,
            last_candle_close=TRIGGER * close_mult,
        )
        assert prices[0] == pytest.approx(
            TRIGGER * close_mult * (1.0 + self.FLOOR / 100.0) * (1.0 + GAP / 100.0),
            rel=1e-12,
        )
        assert placement_pct(+1, prices[0]) > self.FLOOR + EPS

    def test_a_zero_floor_still_means_no_floor(self):
        """A failure means the fibonacci re-anchoring contract broke: at
        a zero MOTD the rungs must follow the candle close alone."""
        a = scrum_ladder_prices(TRIGGER, 5, GAP, "fibonacci", last_candle_close=50.0)
        b = scrum_ladder_prices(180.0, 5, GAP, "fibonacci", last_candle_close=50.0)
        assert a == pytest.approx(b, rel=1e-12)
        assert a[0] == pytest.approx(50.0 * 1.01, rel=1e-12)

    def test_a_positive_floor_makes_the_trigger_price_matter(self):
        """A failure means the floor is measured from the candle close
        rather than from the price the round trip is priced against."""
        a = scrum_ladder_prices(
            TRIGGER,
            5,
            GAP,
            "fibonacci",
            min_opposing_pct=self.FLOOR,
            last_candle_close=50.0,
        )
        b = scrum_ladder_prices(
            180.0,
            5,
            GAP,
            "fibonacci",
            min_opposing_pct=self.FLOOR,
            last_candle_close=50.0,
        )
        assert a != pytest.approx(b, rel=1e-9)
        assert placement_pct(+1, a[0], TRIGGER) == pytest.approx(self.FLOOR, rel=1e-12)
        assert placement_pct(+1, b[0], 180.0) == pytest.approx(self.FLOOR, rel=1e-12)

    def test_PLANT_a_fix_that_always_returns_the_floor_goes_red(self):
        """The control's control: a floor-clamping implementation must
        fail the two assertions above, or they prove nothing."""
        clamped = TRIGGER * (1.0 + self.FLOOR / 100.0)
        with pytest.raises(AssertionError):
            assert clamped == pytest.approx(
                reference_level_one(+1, TRIGGER, GAP, "quadratic", self.FLOOR),
                rel=1e-12,
            )
        with pytest.raises(AssertionError):
            assert placement_pct(+1, clamped) > self.FLOOR + EPS

    def test_PLANT_a_floor_measured_from_the_candle_close_goes_red(self):
        """The control for the fibonacci case: measuring the floor from
        `base` reproduces the defect, and must fail."""
        close = TRIGGER * 0.90
        planted = close * (1.0 + self.FLOOR / 100.0) * (1.0 + GAP / 100.0)
        with pytest.raises(AssertionError):
            assert placement_pct(+1, planted) == pytest.approx(self.FLOOR, rel=1e-12)

    def test_PLANT_a_fix_that_ignores_the_band_goes_red(self):
        """The control for the band half: returning the floor when the
        band sits further out must fail."""
        with pytest.raises(AssertionError):
            assert TRIGGER * (1.0 + self.FLOOR / 100.0) == pytest.approx(
                TRIGGER * 1.12, rel=1e-12
            )


# ---------------------------------------------------------------------------
# The live fleet, swept
# ---------------------------------------------------------------------------


class TestEveryLiveConfigClearsItsOwnFloor:
    """38 real bot configs x 4 spacing modes x both ladder sides."""

    def test_the_fixture_is_the_whole_fleet(self):
        """A failure means the sweep below runs on a slice and reports
        a fleet-wide result."""
        assert FLEET["bot_count"] == 38
        assert len(FLEET["bots"]) == 38
        assert fleet_floor_pcts() == [1.6, 5.6, 6.6]

    def test_no_placement_lands_under_its_own_bots_floor(self):
        """A failure names the bot, mode and side whose tranche cannot
        clear its own round trip."""
        under = []
        for bot in FLEET["bots"]:
            otd = minimum_opposing_trade_distance_pct(
                bot["scrumming_interval_pct"], bot["trading_fee_pct"]
            )
            for mode in SPACING_MODES:
                for d, fn in ((+1, scrum_ladder_prices), (-1, fold_ladder_prices)):
                    kw = {"min_opposing_pct": otd}
                    if mode == "fibonacci":
                        kw["last_candle_close"] = TRIGGER * 0.95
                    got = placement_pct(d, fn(TRIGGER, LEVELS, GAP, mode, **kw)[0])
                    if got + 1e-9 < otd:
                        under.append((bot["symbol"], mode, d, got, otd))
        assert under == [], under

    def test_the_sweep_would_have_caught_the_pre_fix_ladder(self):
        """A failure means the sweep is blind: it must count the 38
        fibonacci scrum placements the unmodified module produced."""
        under = 0
        for bot in FLEET["bots"]:
            otd = minimum_opposing_trade_distance_pct(
                bot["scrumming_interval_pct"], bot["trading_fee_pct"]
            )
            close = TRIGGER * 0.95
            pre_fix = close * (1.0 + otd / 100.0) * (1.0 + GAP / 100.0)
            if placement_pct(+1, pre_fix) + 1e-9 < otd:
                under += 1
        assert under == 38
