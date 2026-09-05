"""Pin tests for src/trading/stack_math.py — pure Stack Mode tranche
generation math. No mocks, no engine — just the pure function under
various inputs.

Locks the operator's spacing law (directive 2026-08-11 / 2026-08-12):
  - The ANCHOR sits min_opposing_pct away from the trigger price
  - Level 1 sits at exactly ONE initial gap from that anchor, and every
    other level is a multiple of the same gap
  - 0.1% merge rule combines adjacent near-identical prices upwards
  - min_order_size reduces tranche count if per-slice size falls below

WHAT THIS FILE USED TO PIN, AND WHY IT NO LONGER DOES. Three classes
below pinned the retired per-STEP law, under which rung 0 sat AT the
anchor at zero offset and quadratic meant the triangular sequence
0, 1, 3, 6. The operator retired both — "Oh, make the quadratic
progression valid then....my math bad..." — and the replacement table
has no 0% level. Each restated test asserts strictly MORE than the one
it replaces: the anchor placement AND the level-1 gap AND agreement
with `ladder_offsets_pct`, where the old test asserted a single number.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.trading.stack_math import (
    DEFAULT_INITIAL_GAP_PCT,
    MERGE_THRESHOLD,
    SPACING_MODES,
    Tranche,
    ladder_offsets_pct,
    scrum_ladder_prices,
    split_scrum_into_tranches,
)

# First-tranche placement


class TestAnchorAndLevelOnePlacement:
    """RESTATES the retired `TestFirstTranchePlacement`.

    Old contract: rung 0 sat AT the anchor, so `result[0].price` was
    `scrum_price × (1 + min_opposing/100)` exactly.
    New contract: the anchor is still at min_opposing, and LEVEL 1 sits
    one initial gap above it. Each test below asserts BOTH halves plus
    an explicit refusal of the retired value, where the old test
    asserted one number.
    """

    def test_anchor_at_min_opposing_and_level_one_one_gap_above(self):
        anchor = 100.0 * (1.0 + 1.0 / 100.0)
        result = split_scrum_into_tranches(
            scrum_price=100.0,
            scrum_size=10.0,
            n_target=3,
            split_distance_pct=1.0,
            spacing_mode="linear",
            min_opposing_pct=1.0,
        )
        assert result[0].price == pytest.approx(
            anchor * 1.01, rel=1e-12
        ), "level 1 must sit exactly one initial gap above the anchor"
        assert result[0].price != pytest.approx(anchor, rel=1e-12), (
            "retired contract: no rung sits AT the anchor; the operator's "
            "table has no 0% level"
        )

    def test_anchor_at_min_opposing_larger(self):
        anchor = 1000.0 * (1.0 + 3.0 / 100.0)
        result = split_scrum_into_tranches(
            scrum_price=1000.0,
            scrum_size=10.0,
            n_target=3,
            split_distance_pct=1.0,
            spacing_mode="linear",
            min_opposing_pct=3.0,
        )
        assert anchor == pytest.approx(1030.0, rel=1e-12)
        assert result[0].price == pytest.approx(1030.0 * 1.01, rel=1e-12)

    def test_zero_opposing_puts_level_one_one_gap_above_scrum_price(self):
        """With no opposing distance the anchor IS the trigger price, so
        level 1 lands at exactly the initial gap — the operator's
        `level 1 = 1%` row, read straight off the trigger price."""
        result = split_scrum_into_tranches(
            scrum_price=100.0,
            scrum_size=10.0,
            n_target=3,
            split_distance_pct=1.0,
            spacing_mode="linear",
            min_opposing_pct=0.0,
        )
        assert result[0].price == pytest.approx(101.0, rel=1e-12)

    def test_level_one_is_the_gap_for_every_mode(self):
        """multiplier(mode, 1) == 1 in all four modes, so level 1 is the
        initial gap whichever mode is selected. This is the property the
        three cases above sample."""
        for mode in SPACING_MODES:
            offsets = ladder_offsets_pct(4, DEFAULT_INITIAL_GAP_PCT, mode)
            assert offsets[0] == pytest.approx(
                1.0, rel=1e-12
            ), f"mode {mode!r}: level 1 must sit at exactly the initial gap"


# Spacing model math (operator's Δp sequences)


class TestSpacingModelSequences:
    """RESTATES the retired per-STEP sequences.

    Old contract (cumulative offsets, rung 0 at the anchor):
        linear 0,1,2,3 · quadratic 0,1,3,6 · exponential 0,1,3,7
    New contract (distance of LEVEL n from the anchor, n from 1):
        linear 1,2,3,4 · quadratic 1,4,9,16 · fibonacci 1,2,3,5
        · exponential 1,2,4,8
    The middle row is the correction: 0,1,3,6 is the triangular
    sequence, not a quadratic one. Each restated test now also asserts
    the tranche prices agree with `ladder_offsets_pct`, coupling the
    shipped ladder to the published law rather than to a literal.
    """

    def _deltas(self, tranches: list[Tranche], anchor: float) -> list[float]:
        """Return each tranche's distance from `anchor`, in percent."""
        return [(t.price / anchor - 1.0) * 100.0 for t in tranches]

    def _assert_matches_law(self, mode: str, gap: float, expected: list[float]):
        # Fibonacci anchors on the last candle close, set equal to the trigger
        # price so all four sequences are read off 100.0.
        r = split_scrum_into_tranches(
            scrum_price=100.0,
            scrum_size=100.0,
            n_target=len(expected),
            split_distance_pct=gap,
            spacing_mode=mode,
            min_opposing_pct=0.0,
            last_candle_close=100.0,
        )
        deltas = self._deltas(r, 100.0)
        assert deltas == pytest.approx(expected, abs=1e-9)
        assert ladder_offsets_pct(len(expected), gap, mode) == pytest.approx(
            expected, abs=1e-9
        ), (
            f"{mode}: the shipped ladder and the published offset law "
            f"must not disagree"
        )

    def test_linear_distances(self):
        self._assert_matches_law("linear", 1.0, [1.0, 2.0, 3.0, 4.0])

    def test_quadratic_distances(self):
        """n^2 x gap. The retired 0, 1, 3, 6 was triangular."""
        self._assert_matches_law("quadratic", 1.0, [1.0, 4.0, 9.0, 16.0])

    def test_fibonacci_distances(self):
        self._assert_matches_law("fibonacci", 1.0, [1.0, 2.0, 3.0, 5.0])

    def test_exponential_distances(self):
        """r^(n-1) x gap with the default r=2."""
        self._assert_matches_law("exponential", 1.0, [1.0, 2.0, 4.0, 8.0])

    def test_split_distance_scales(self):
        """Doubling the initial gap doubles EVERY distance, level 1
        included — the old version skipped index 0 because index 0 was
        pinned at zero and could not scale."""
        d1 = self._deltas(
            split_scrum_into_tranches(
                scrum_price=100.0,
                scrum_size=100.0,
                n_target=4,
                split_distance_pct=1.0,
                spacing_mode="quadratic",
                min_opposing_pct=0.0,
            ),
            100.0,
        )
        d2 = self._deltas(
            split_scrum_into_tranches(
                scrum_price=100.0,
                scrum_size=100.0,
                n_target=4,
                split_distance_pct=2.0,
                spacing_mode="quadratic",
                min_opposing_pct=0.0,
            ),
            100.0,
        )
        assert len(d1) == 4
        for a, b in zip(d1, d2):
            assert b == pytest.approx(a * 2.0, abs=1e-9)


# Invariants: monotone, sum, count


class TestInvariants:
    def test_prices_are_monotone_increasing(self):
        r = split_scrum_into_tranches(
            scrum_price=100.0,
            scrum_size=100.0,
            n_target=5,
            split_distance_pct=1.5,
            spacing_mode="quadratic",
            min_opposing_pct=1.0,
        )
        for i in range(1, len(r)):
            assert r[i].price > r[i - 1].price

    def test_sum_of_sizes_equals_scrum_size(self):
        r = split_scrum_into_tranches(
            scrum_price=100.0,
            scrum_size=50.0,
            n_target=5,
            split_distance_pct=1.0,
            spacing_mode="linear",
            min_opposing_pct=1.0,
        )
        total = sum(t.size for t in r)
        assert total == pytest.approx(50.0, abs=1e-9)

    def test_indices_are_zero_based_and_contiguous(self):
        r = split_scrum_into_tranches(
            scrum_price=100.0,
            scrum_size=100.0,
            n_target=4,
            split_distance_pct=1.0,
            spacing_mode="linear",
            min_opposing_pct=1.0,
        )
        assert [t.index for t in r] == list(range(len(r)))


# 0.1% merge rule


class TestMergeRule:
    def test_two_tranches_below_threshold_merge(self):
        """SD=0.05% (below 0.1% threshold) → adjacent tranches merge."""
        r = split_scrum_into_tranches(
            scrum_price=100.0,
            scrum_size=100.0,
            n_target=4,
            split_distance_pct=0.05,
            spacing_mode="linear",
            min_opposing_pct=0.0,
        )
        # With SD=0.05%, all Δp between adjacent tranches = 0.05% < 0.1%.
        # All 4 should merge into 1.
        assert len(r) == 1, f"expected 1 tranche after merge, got {len(r)}"
        assert r[0].size == pytest.approx(100.0, abs=1e-9)

    def test_merged_price_is_the_higher_one(self):
        """When two tranches merge, the surviving price is the higher.

        RESTATED: the expected value now comes from
        `scrum_ladder_prices` rather than from the literal 100.05, so
        the test pins "the survivor is the ladder's higher rung" instead
        of "the survivor is this number". Under the retired law the two
        rungs were 100.00 and 100.05; under the current one they are
        100.05 and 100.10. The invariant is unchanged either way.
        """
        rungs = scrum_ladder_prices(100.0, 2, 0.05, "linear", min_opposing_pct=0.0)
        r = split_scrum_into_tranches(
            scrum_price=100.0,
            scrum_size=100.0,
            n_target=2,
            split_distance_pct=0.05,
            spacing_mode="linear",
            min_opposing_pct=0.0,
        )
        assert len(r) == 1, "0.05% apart is inside the 0.1% merge band"
        assert r[0].price == pytest.approx(max(rungs), abs=1e-9)
        assert r[0].price > min(rungs)

    def test_merged_size_is_sum(self):
        r = split_scrum_into_tranches(
            scrum_price=100.0,
            scrum_size=20.0,
            n_target=2,
            split_distance_pct=0.05,
            spacing_mode="linear",
            min_opposing_pct=0.0,
        )
        assert r[0].size == pytest.approx(20.0, abs=1e-9)

    def test_above_threshold_no_merge(self):
        r = split_scrum_into_tranches(
            scrum_price=100.0,
            scrum_size=100.0,
            n_target=4,
            split_distance_pct=0.2,
            spacing_mode="linear",
            min_opposing_pct=0.0,
        )
        assert len(r) == 4


# min_order_size restriction


class TestMinOrderSize:
    def test_below_min_reduces_tranche_count(self):
        """scrum_size=1.0, N=4, min=0.5 → floor(1.0/0.5) = 2 tranches."""
        r = split_scrum_into_tranches(
            scrum_price=100.0,
            scrum_size=1.0,
            n_target=4,
            split_distance_pct=1.0,
            spacing_mode="linear",
            min_opposing_pct=0.0,
            min_order_size=0.5,
        )
        assert len(r) == 2
        # Each tranche = 1.0 / 2 = 0.5
        assert r[0].size == pytest.approx(0.5, abs=1e-9)
        assert r[1].size == pytest.approx(0.5, abs=1e-9)

    def test_min_of_zero_disables_restriction(self):
        r = split_scrum_into_tranches(
            scrum_price=100.0,
            scrum_size=1.0,
            n_target=10,
            split_distance_pct=1.0,
            spacing_mode="linear",
            min_opposing_pct=0.0,
            min_order_size=0.0,
        )
        assert len(r) == 10

    def test_total_size_below_min_collapses_to_one(self):
        """If scrum_size < min_order_size entirely, return single tranche
        holding total_size — caller decides whether to fire it."""
        r = split_scrum_into_tranches(
            scrum_price=100.0,
            scrum_size=0.3,
            n_target=4,
            split_distance_pct=1.0,
            spacing_mode="linear",
            min_opposing_pct=0.0,
            min_order_size=0.5,
        )
        assert len(r) == 1
        assert r[0].size == pytest.approx(0.3, abs=1e-9)


# Input validation


class TestInputValidation:
    def test_zero_scrum_price_raises(self):
        with pytest.raises(ValueError, match="scrum_price"):
            split_scrum_into_tranches(
                scrum_price=0.0,
                scrum_size=10.0,
                n_target=3,
                split_distance_pct=1.0,
                spacing_mode="linear",
                min_opposing_pct=0.0,
            )

    def test_zero_scrum_size_raises(self):
        with pytest.raises(ValueError, match="scrum_size"):
            split_scrum_into_tranches(
                scrum_price=100.0,
                scrum_size=0.0,
                n_target=3,
                split_distance_pct=1.0,
                spacing_mode="linear",
                min_opposing_pct=0.0,
            )

    def test_zero_n_target_raises(self):
        with pytest.raises(ValueError, match="n_target"):
            split_scrum_into_tranches(
                scrum_price=100.0,
                scrum_size=10.0,
                n_target=0,
                split_distance_pct=1.0,
                spacing_mode="linear",
                min_opposing_pct=0.0,
            )

    def test_unknown_spacing_mode_raises(self):
        """RESTATED: the old probe used "fibonacci", which is now one of
        the four supported modes. Testing the same invariant with a name
        that later becomes valid turns the guard green by accident, so
        the probe is now several never-valid names AND a positive half
        proving every real mode is accepted."""
        for bogus in ("logarithmic", "sinusoidal", "", "QUADRATIC", None):
            with pytest.raises(ValueError, match="spacing_mode"):
                split_scrum_into_tranches(
                    scrum_price=100.0,
                    scrum_size=10.0,
                    n_target=3,
                    split_distance_pct=1.0,
                    spacing_mode=bogus,
                    min_opposing_pct=0.0,
                )

    def test_every_supported_spacing_mode_is_accepted(self):
        """The positive half of the guard above: a mode list that
        rejects everything would pass the negative half alone."""
        assert set(SPACING_MODES) == {"quadratic", "fibonacci", "linear", "exponential"}
        for mode in SPACING_MODES:
            r = split_scrum_into_tranches(
                scrum_price=100.0,
                scrum_size=10.0,
                n_target=3,
                split_distance_pct=1.0,
                spacing_mode=mode,
                min_opposing_pct=0.0,
                last_candle_close=100.0,
            )
            assert len(r) == 3, f"mode {mode!r} did not build a 3-rung ladder"

    def test_negative_split_distance_raises(self):
        with pytest.raises(ValueError, match="split_distance_pct"):
            split_scrum_into_tranches(
                scrum_price=100.0,
                scrum_size=10.0,
                n_target=3,
                split_distance_pct=-1.0,
                spacing_mode="linear",
                min_opposing_pct=0.0,
            )


# to_dict serialization (for the runtime ledger + GUI)


class TestSerialization:
    def test_tranche_to_dict_has_expected_keys(self):
        r = split_scrum_into_tranches(
            scrum_price=100.0,
            scrum_size=10.0,
            n_target=1,
            split_distance_pct=1.0,
            spacing_mode="linear",
            min_opposing_pct=1.0,
        )
        d = r[0].to_dict()
        assert set(d.keys()) == {"index", "price", "size"}


# Constants


class TestConstants:
    def test_merge_threshold_is_one_tenth_percent(self):
        assert MERGE_THRESHOLD == 0.001, (
            "operator directive 2026-07-25: tranches within 0.1% "
            "combine upwards. Constant must stay 0.001."
        )
