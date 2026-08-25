"""Item 6 — the four ladder spacing modes, on both sides of the ladder.

Pins the operator's spacing law (directive 2026-08-11 / 2026-08-12):

    distance(level n) = multiplier(mode, n) x initial_gap_pct

    quadratic     n^2                     DEFAULT
    fibonacci     1, 2, 3, 5, 8, 13, 21   from the LAST CANDLE CLOSE
    linear        n
    exponential   r^(n-1), r default 2

and the two rules that ride with it:

  * "Both side should be quadratically laddered with the initial gap
     being 1%" / "Functionality should be mirrored between either side
     of the ladder."
  * "the initial position for any such spaced stack must have the
     additional rule of not being able to be outside of the local BB
     range but subsequent positions are allowed to extend beyond these
     bounds."

SPACING ONLY. Nothing here tests merge, distribution or consumption.

Every check here has a paired control. Some controls live in the file
as the negative half written beside the positive one — a mode list that
accepted nothing would pass every "unknown mode raises" test on its own,
so there is a test that every real mode IS accepted. The rest are
planted defects in the module under test, each mutated in turn with the
suite re-run to observe this file go red, then reverted and the source
hash compared to prove the revert was byte-identical.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.trading.stack_math import (
    DEFAULT_EXPONENTIAL_RATIO,
    DEFAULT_INITIAL_GAP_PCT,
    DEFAULT_SPACING_MODE,
    MAX_FOLD_DISTANCE_PCT,
    SPACING_MODES,
    fold_ladder_prices,
    ladder_offsets_pct,
    level_multipliers,
    scrum_ladder_prices,
    split_scrum_into_tranches,
)

# The operator's table, verbatim.
OPERATOR_QUADRATIC_TABLE_PCT = [1.0, 4.0, 9.0, 16.0, 25.0, 36.0, 49.0]
OPERATOR_QUADRATIC_GAPS_PCT = [1.0, 3.0, 5.0, 7.0, 9.0, 11.0, 13.0]

FIBONACCI_MULTIPLIERS = [1.0, 2.0, 3.0, 5.0, 8.0, 13.0, 21.0]


def _gaps(distances: list[float]) -> list[float]:
    """Gap between consecutive levels; level 1's gap is its distance."""
    out = [distances[0]]
    out.extend(b - a for a, b in zip(distances, distances[1:]))
    return out


# ---------------------------------------------------------------------------
# The default, and the operator's table
# ---------------------------------------------------------------------------


class TestQuadraticIsTheDefault:
    def test_default_mode_is_quadratic(self):
        assert DEFAULT_SPACING_MODE == "quadratic"
        assert SPACING_MODES[0] == "quadratic"

    def test_default_initial_gap_is_one_percent(self):
        assert DEFAULT_INITIAL_GAP_PCT == 1.0

    def test_calling_with_no_mode_gives_the_quadratic_table(self):
        """The default path, taken by a caller that names neither the
        mode nor the gap, must land on the operator's table."""
        assert ladder_offsets_pct(7) == OPERATOR_QUADRATIC_TABLE_PCT


class TestOperatorQuadraticTable:
    def test_table_reproduces_exactly(self):
        """1/4/9/16/25/36/49 at a 1% gap — exact equality, not approx.

        These values are exactly representable in binary floating point,
        so `approx` here would only hide a real deviation.
        """
        assert ladder_offsets_pct(7, 1.0, "quadratic") == OPERATOR_QUADRATIC_TABLE_PCT

    def test_gap_row_reproduces_exactly(self):
        """The second row of the operator's table: 1/3/5/7/9/11/13."""
        assert (
            _gaps(ladder_offsets_pct(7, 1.0, "quadratic"))
            == OPERATOR_QUADRATIC_GAPS_PCT
        )

    def test_level_seven_needs_a_forty_nine_percent_move(self):
        """The arc steepens fast, and the reach is a property of the
        table rather than a comment about it."""
        assert ladder_offsets_pct(7, 1.0, "quadratic")[-1] == 49.0

    def test_shipped_ladder_matches_the_table(self):
        """The table is only worth pinning if the built ladder obeys it.
        Read at the surface the caller consumes: tranche prices."""
        prices = scrum_ladder_prices(100.0, 7, 1.0, "quadratic", min_opposing_pct=0.0)
        expected = [100.0 * (1.0 + d / 100.0) for d in OPERATOR_QUADRATIC_TABLE_PCT]
        assert prices == pytest.approx(expected, rel=1e-12)


class TestQuadraticIsQuadraticNotMerelyRising:
    """The property, not the table. A sequence that only grows faster
    each step is not quadratic — the retired triangular 1/3/6/10 grew
    too. What makes it quadratic is a CONSTANT second difference.
    """

    def test_second_difference_is_two_gaps_at_the_default(self):
        d = ladder_offsets_pct(7, 1.0, "quadratic")
        second = [c - 2 * b + a for a, b, c in zip(d, d[1:], d[2:])]
        assert second == [2.0] * 5

    @pytest.mark.parametrize("gap", [0.1, 0.25, 1.0, 1.6, 3.75, 12.5, 20.0])
    def test_second_difference_is_two_gaps_at_any_gap(self, gap):
        d = ladder_offsets_pct(12, gap, "quadratic")
        second = [c - 2 * b + a for a, b, c in zip(d, d[1:], d[2:])]
        assert second == pytest.approx([2.0 * gap] * len(second), rel=1e-9)

    @pytest.mark.parametrize("mode", ["linear", "exponential", "fibonacci"])
    def test_no_other_mode_has_that_constant_second_difference(self, mode):
        """The control for the two tests above. If every mode satisfied
        the property, the property would identify nothing.

        Linear's second difference is a constant ZERO, which is not
        `2 x gap`; the other two are not constant at all.
        """
        d = ladder_offsets_pct(12, 1.0, mode)
        second = [c - 2 * b + a for a, b, c in zip(d, d[1:], d[2:])]
        assert second != pytest.approx([2.0] * len(second), rel=1e-9)


# ---------------------------------------------------------------------------
# The initial gap is configurable
# ---------------------------------------------------------------------------


class TestInitialGapIsConfigurable:
    @pytest.mark.parametrize("gap", [0.1, 0.5, 2.0, 2.5, 7.25, 20.0])
    @pytest.mark.parametrize("mode", list(SPACING_MODES))
    def test_every_level_scales_with_the_gap(self, gap, mode):
        """A non-default gap multiplies EVERY level, level 1 included."""
        unit = ladder_offsets_pct(9, 1.0, mode)
        scaled = ladder_offsets_pct(9, gap, mode)
        assert scaled == pytest.approx([u * gap for u in unit], rel=1e-12)

    @pytest.mark.parametrize("gap", [0.1, 0.5, 2.0, 2.5, 7.25, 20.0])
    def test_level_one_is_exactly_the_gap(self, gap):
        for mode in SPACING_MODES:
            assert ladder_offsets_pct(9, gap, mode)[0] == pytest.approx(
                gap, rel=1e-12
            ), f"{mode}: level 1 must be one gap"

    def test_a_non_default_gap_reaches_the_built_ladder(self):
        """Scaling the offset law is worth nothing if the builder holds
        a hard-coded 1%. Checked at the tranche price."""
        r = split_scrum_into_tranches(
            scrum_price=200.0,
            scrum_size=9.0,
            n_target=3,
            split_distance_pct=2.5,
            spacing_mode="quadratic",
            min_opposing_pct=0.0,
        )
        assert [t.price for t in r] == pytest.approx(
            [200.0 * 1.025, 200.0 * 1.10, 200.0 * 1.225], rel=1e-12
        )


# ---------------------------------------------------------------------------
# Each mode's own stated sequence
# ---------------------------------------------------------------------------


class TestEachModeHasItsOwnSequence:
    def test_linear(self):
        assert ladder_offsets_pct(7, 1.0, "linear") == [
            1.0,
            2.0,
            3.0,
            4.0,
            5.0,
            6.0,
            7.0,
        ]

    def test_exponential_default_ratio(self):
        assert DEFAULT_EXPONENTIAL_RATIO == 2.0
        assert ladder_offsets_pct(7, 1.0, "exponential") == [
            1.0,
            2.0,
            4.0,
            8.0,
            16.0,
            32.0,
            64.0,
        ]

    def test_exponential_honours_a_custom_ratio(self):
        assert ladder_offsets_pct(4, 1.0, "exponential", 3.0) == [1.0, 3.0, 9.0, 27.0]

    def test_exponential_refuses_a_non_rising_ratio(self):
        for bad in (1.0, 0.5, 0.0, -2.0):
            with pytest.raises(ValueError, match="exponential_ratio"):
                ladder_offsets_pct(4, 1.0, "exponential", bad)

    def test_fibonacci(self):
        assert ladder_offsets_pct(7, 1.0, "fibonacci") == FIBONACCI_MULTIPLIERS

    def test_fibonacci_each_term_is_the_sum_of_the_previous_two(self):
        """The property behind the table."""
        f = ladder_offsets_pct(12, 1.0, "fibonacci")
        for a, b, c in zip(f, f[1:], f[2:]):
            assert c == pytest.approx(a + b, rel=1e-12)

    def test_the_four_sequences_are_distinct(self):
        """The control: four names in front of one sequence would pass
        every individual test above."""
        seqs = {m: tuple(ladder_offsets_pct(7, 1.0, m)) for m in SPACING_MODES}
        assert len(set(seqs.values())) == 4, seqs

    def test_level_multipliers_and_offsets_agree(self):
        for mode in SPACING_MODES:
            mult = level_multipliers(mode, 8)
            offs = ladder_offsets_pct(8, 3.0, mode)
            assert offs == pytest.approx([m * 3.0 for m in mult], rel=1e-12)


# ---------------------------------------------------------------------------
# Fibonacci is measured from the last candle close
# ---------------------------------------------------------------------------


class TestFibonacciMovesWithTheCandleClose:
    def test_no_candle_close_is_refused(self):
        """A fibonacci ladder anchored on the trigger price would be
        static. Refused rather than silently faked."""
        with pytest.raises(ValueError, match="last candle close"):
            scrum_ladder_prices(100.0, 5, 1.0, "fibonacci")

    def test_levels_move_when_the_candle_closes_elsewhere(self):
        a = scrum_ladder_prices(100.0, 5, 1.0, "fibonacci", last_candle_close=100.0)
        b = scrum_ladder_prices(100.0, 5, 1.0, "fibonacci", last_candle_close=110.0)
        assert a != pytest.approx(
            b, rel=1e-9
        ), "the whole point of the mode: a new close moves the rungs"
        # They move BY the close, exactly — not by some other amount.
        assert b == pytest.approx([p * 1.1 for p in a], rel=1e-12)

    def test_the_offsets_themselves_do_not_move(self):
        """Only the anchor moves. The spacing law is unchanged by a new
        candle, which is what makes the movement a re-anchor rather than
        a different ladder."""
        for close in (50.0, 100.0, 137.42):
            prices = scrum_ladder_prices(
                100.0, 5, 1.0, "fibonacci", last_candle_close=close
            )
            expected = [close * (1.0 + m / 100.0) for m in FIBONACCI_MULTIPLIERS[:5]]
            assert prices == pytest.approx(expected, rel=1e-12)

    def test_the_trigger_price_does_not_anchor_a_fibonacci_ladder(self):
        """The control for the two tests above: if the builder quietly
        anchored on the trigger price, moving the trigger would move the
        rungs. It must not."""
        a = scrum_ladder_prices(100.0, 5, 1.0, "fibonacci", last_candle_close=100.0)
        b = scrum_ladder_prices(180.0, 5, 1.0, "fibonacci", last_candle_close=100.0)
        assert a == pytest.approx(b, rel=1e-12)

    def test_other_modes_do_not_need_a_close(self):
        for mode in ("quadratic", "linear", "exponential"):
            assert len(scrum_ladder_prices(100.0, 4, 1.0, mode)) == 4


# ---------------------------------------------------------------------------
# The BB constraint
# ---------------------------------------------------------------------------


class TestLevelOneMustSitInsideTheBand:
    BAND = (99.0, 101.0)

    def test_level_one_inside_the_band_is_accepted(self):
        prices = scrum_ladder_prices(100.0, 3, 0.5, "quadratic", bb_bounds=self.BAND)
        assert prices[0] == pytest.approx(100.5, rel=1e-12)
        assert self.BAND[0] <= prices[0] <= self.BAND[1]

    def test_level_one_outside_the_band_is_refused(self):
        """A 5% initial gap puts level 1 at 105 against a 101 upper."""
        with pytest.raises(ValueError, match="outside the local BB range"):
            scrum_ladder_prices(100.0, 3, 5.0, "quadratic", bb_bounds=self.BAND)

    def test_levels_two_and_up_may_extend_beyond_the_band(self):
        """Operator: subsequent positions are allowed to extend beyond
        these bounds. Level 2 at +2% clears the 101 upper and the ladder
        is still returned."""
        prices = scrum_ladder_prices(100.0, 3, 0.5, "quadratic", bb_bounds=self.BAND)
        assert prices[1] > self.BAND[1]
        assert prices[2] > self.BAND[1]
        assert len(prices) == 3

    def test_the_fold_side_enforces_the_same_rule(self):
        assert fold_ladder_prices(100.0, 3, 0.5, "quadratic", bb_bounds=self.BAND)[
            0
        ] == (pytest.approx(99.5, rel=1e-12))
        with pytest.raises(ValueError, match="outside the local BB range"):
            fold_ladder_prices(100.0, 3, 5.0, "quadratic", bb_bounds=self.BAND)

    def test_the_fold_side_lets_levels_two_and_up_out_of_the_band(self):
        prices = fold_ladder_prices(100.0, 3, 0.5, "quadratic", bb_bounds=self.BAND)
        assert prices[1] < self.BAND[0]
        assert prices[2] < self.BAND[0]

    def test_no_band_means_the_rule_is_not_enforced_not_that_one_was_invented(self):
        """Pinned deliberately. With no band the module does NOT compute
        one and does NOT fall back to a made-up range: the same ladder
        that is refused against a supplied band is built without one.
        The caller is the only thing that knows whether a band exists.
        """
        refused_shape = scrum_ladder_prices(100.0, 3, 5.0, "quadratic")
        assert refused_shape[0] == pytest.approx(105.0, rel=1e-12)

    def test_a_malformed_band_is_refused_rather_than_ignored(self):
        for bad in (
            (101.0, 99.0),
            (0.0, 101.0),
            (-5.0, -1.0),
            (100.0,),
            (99.0, 100.0, 101.0),
            99.0,
        ):
            with pytest.raises(ValueError, match="bb_bounds"):
                scrum_ladder_prices(100.0, 3, 0.5, "quadratic", bb_bounds=bad)

    def test_the_rule_reaches_the_tranche_builder(self):
        """Read at the surface the SCRUM path consumes."""
        with pytest.raises(ValueError, match="outside the local BB range"):
            split_scrum_into_tranches(
                scrum_price=100.0,
                scrum_size=9.0,
                n_target=3,
                split_distance_pct=5.0,
                spacing_mode="quadratic",
                bb_bounds=self.BAND,
            )


# ---------------------------------------------------------------------------
# Both sides, mirrored
# ---------------------------------------------------------------------------


class TestBothSidesAreMirrored:
    SETTINGS = dict(levels=6, initial_gap_pct=1.0, spacing_mode="quadratic")

    def _pair(self, **over):
        kw = {"trigger_price": 100.0, **self.SETTINGS, **over}
        return (scrum_ladder_prices(**kw), fold_ladder_prices(**kw))

    def test_the_two_sides_walk_opposite_ways(self):
        up, down = self._pair()
        assert up == sorted(up)
        assert down == sorted(down, reverse=True)

    @pytest.mark.parametrize("mode", list(SPACING_MODES))
    def test_displacements_are_equal_and_opposite(self, mode):
        kw = dict(
            trigger_price=100.0,
            levels=6,
            initial_gap_pct=1.0,
            spacing_mode=mode,
            last_candle_close=100.0,
        )
        up = scrum_ladder_prices(**kw)
        down = fold_ladder_prices(**kw)
        for u, d in zip(up, down):
            assert (u - 100.0) == pytest.approx(100.0 - d, rel=1e-12)

    @pytest.mark.parametrize("mode", list(SPACING_MODES))
    def test_both_sides_read_the_same_offsets(self, mode):
        """Compared as PRICES against prices rebuilt from the published
        offsets, rather than by dividing each price back down into a
        percentage. Same claim, and it does not mix a normalised
        quantity with an absolute one to make it."""
        offs = ladder_offsets_pct(6, 1.0, mode)
        kw = dict(
            trigger_price=100.0,
            levels=6,
            initial_gap_pct=1.0,
            spacing_mode=mode,
            last_candle_close=100.0,
        )
        up = scrum_ladder_prices(**kw)
        down = fold_ladder_prices(**kw)
        assert up == pytest.approx([100.0 * (1.0 + o / 100.0) for o in offs], rel=1e-12)
        assert down == pytest.approx(
            [100.0 * (1.0 - o / 100.0) for o in offs], rel=1e-12
        )

    def test_the_opposing_distance_mirrors_too(self):
        """`min_opposing_pct` pushes the SCRUM anchor up and the FOLD
        anchor down by the same percentage."""
        up = scrum_ladder_prices(100.0, 3, 1.0, "quadratic", min_opposing_pct=1.6)
        down = fold_ladder_prices(100.0, 3, 1.0, "quadratic", min_opposing_pct=1.6)
        assert up[0] == pytest.approx(101.6 * 1.01, rel=1e-12)
        assert down[0] == pytest.approx(98.4 * 0.99, rel=1e-12)

    def test_a_fold_rung_can_never_be_priced_at_or_below_zero(self):
        """The fold side walks DOWN, so a 100%-or-worse distance is not
        a price. Refused loudly, never clamped to something plausible.
        """
        assert MAX_FOLD_DISTANCE_PCT == 100.0
        with pytest.raises(ValueError, match="fold rung cannot be"):
            fold_ladder_prices(100.0, 10, 1.0, "quadratic")
        # The control: the SAME settings are legal going up.
        assert min(scrum_ladder_prices(100.0, 10, 1.0, "quadratic")) > 0

    def test_the_reachable_fold_ladder_is_returned_in_full(self):
        """The refusal above must not be a blanket one: nine quadratic
        levels at 1% top out at 81% and are all real prices."""
        prices = fold_ladder_prices(100.0, 9, 1.0, "quadratic")
        assert len(prices) == 9
        assert all(p > 0 for p in prices)
        assert prices[-1] == pytest.approx(19.0, rel=1e-12)


# ---------------------------------------------------------------------------
# What counts as a number
# ---------------------------------------------------------------------------


class TestNumericAdmission:
    """A rung is a threshold PRICE, so what may become one matters.

    `isinstance(x, (int, float))` admits `bool`, and `float('20.0')` is
    20.0. Both shapes have reached money-handling code in this repo
    before. Added after a planted `isinstance` guard survived the whole
    suite green: the exact-type test had no control of its own.
    """

    NOT_A_NUMBER = [True, False, "1.0", "20.0", None, [1.0], (1.0,)]

    @pytest.mark.parametrize("bad", NOT_A_NUMBER)
    def test_a_gap_that_is_not_a_number_is_refused(self, bad):
        with pytest.raises(ValueError, match="initial_gap_pct"):
            ladder_offsets_pct(3, bad, "quadratic")

    @pytest.mark.parametrize("bad", NOT_A_NUMBER)
    def test_a_trigger_price_that_is_not_a_number_is_refused(self, bad):
        with pytest.raises(ValueError, match="trigger_price"):
            scrum_ladder_prices(bad, 3, 1.0, "quadratic")

    @pytest.mark.parametrize("bad", NOT_A_NUMBER)
    def test_an_opposing_distance_that_is_not_a_number_is_refused(self, bad):
        with pytest.raises(ValueError, match="min_opposing_pct"):
            fold_ladder_prices(100.0, 3, 1.0, "quadratic", min_opposing_pct=bad)

    @pytest.mark.parametrize("bad", [True, False, 3.0, "3", None])
    def test_a_level_count_that_is_not_an_int_is_refused(self, bad):
        with pytest.raises(ValueError, match="levels"):
            ladder_offsets_pct(bad, 1.0, "quadratic")

    @pytest.mark.parametrize("bad", [True, False, 3.0, "3", None])
    def test_the_tranche_builder_refuses_the_same_shapes(self, bad):
        with pytest.raises(ValueError, match="n_target"):
            split_scrum_into_tranches(scrum_price=100.0, scrum_size=9.0, n_target=bad)

    def test_real_numbers_are_still_accepted(self):
        """The control. A guard that refused everything would pass every
        test above and break the product."""
        assert ladder_offsets_pct(3, 1, "quadratic") == [1.0, 4.0, 9.0]
        assert ladder_offsets_pct(3, 1.0, "quadratic") == [1.0, 4.0, 9.0]
        assert len(scrum_ladder_prices(100, 3, 1, "quadratic")) == 3
        assert (
            len(fold_ladder_prices(100.0, 3, 1.0, "quadratic", min_opposing_pct=0)) == 3
        )


# ---------------------------------------------------------------------------
# Rule 2 — sweep the numeric domain rather than hand-writing rows
# ---------------------------------------------------------------------------


def _fib_reference(levels: int) -> list[float]:
    out, a, b = [], 1.0, 2.0
    for _ in range(levels):
        out.append(a)
        a, b = b, a + b
    return out


def _expected_multipliers(mode: str, levels: int) -> list[float]:
    if mode == "quadratic":
        return [float(n * n) for n in range(1, levels + 1)]
    if mode == "linear":
        return [float(n) for n in range(1, levels + 1)]
    if mode == "fibonacci":
        return _fib_reference(levels)
    return [2.0 ** (n - 1) for n in range(1, levels + 1)]


class TestSweepTheThresholdDomain:
    """These are threshold PRICES. An eight-row accept/reject table in
    this repo once passed while a 2,868-case sweep found 113 silent
    behaviour changes, one of them a zero-size live order. So the level
    count and the initial gap are swept across their real ranges and the
    stated property is asserted at every point.

    Ranges are the ones the operator can actually select: the Tranche
    Count spin box is 2..20 and the Split Distance spin box is
    0.10..20.00 in 0.01 steps.
    """

    COUNTS = range(2, 21)
    GAP_STEPS = range(10, 2001, 5)  # 0.10% .. 20.00% in 0.05% steps

    def test_every_mode_at_every_count_and_gap(self):
        points = 0
        for mode in SPACING_MODES:
            for levels in self.COUNTS:
                expected = _expected_multipliers(mode, levels)
                for step in self.GAP_STEPS:
                    gap = step / 100.0
                    offs = ladder_offsets_pct(levels, gap, mode)
                    points += 1
                    assert len(offs) == levels
                    assert offs[0] == pytest.approx(gap, rel=1e-12), (
                        f"{mode} n={levels} gap={gap}: level 1 must be " f"one gap"
                    )
                    assert offs == pytest.approx(
                        [m * gap for m in expected], rel=1e-9
                    ), f"{mode} n={levels} gap={gap}: sequence drift"
                    assert all(
                        b > a for a, b in zip(offs, offs[1:])
                    ), f"{mode} n={levels} gap={gap}: not increasing"
        assert points == len(SPACING_MODES) * len(self.COUNTS) * len(self.GAP_STEPS)

    def test_quadratic_second_difference_over_the_whole_domain(self):
        for levels in self.COUNTS:
            if levels < 3:
                continue
            for step in self.GAP_STEPS:
                gap = step / 100.0
                d = ladder_offsets_pct(levels, gap, "quadratic")
                second = [c - 2 * b + a for a, b, c in zip(d, d[1:], d[2:])]
                assert second == pytest.approx([2.0 * gap] * len(second), rel=1e-9), (
                    f"quadratic n={levels} gap={gap}: second difference "
                    f"is not a constant 2 x gap"
                )

    def test_the_two_sides_mirror_over_the_whole_reachable_domain(self):
        checked = refused = 0
        for mode in SPACING_MODES:
            for levels in self.COUNTS:
                for step in self.GAP_STEPS:
                    gap = step / 100.0
                    offs = ladder_offsets_pct(levels, gap, mode)
                    kw = dict(
                        trigger_price=100.0,
                        levels=levels,
                        initial_gap_pct=gap,
                        spacing_mode=mode,
                        last_candle_close=100.0,
                    )
                    up = scrum_ladder_prices(**kw)
                    if max(offs) >= MAX_FOLD_DISTANCE_PCT:
                        refused += 1
                        with pytest.raises(ValueError, match="fold rung cannot be"):
                            fold_ladder_prices(**kw)
                        continue
                    down = fold_ladder_prices(**kw)
                    checked += 1
                    assert all(p > 0 for p in down)
                    for u, d in zip(up, down):
                        assert (u - 100.0) == pytest.approx(
                            100.0 - d, rel=1e-9
                        ), f"{mode} n={levels} gap={gap}: sides differ"
        # Both halves must be non-empty, or the sweep only exercised one
        # branch and proves nothing about the other.
        assert checked > 0
        assert refused > 0
