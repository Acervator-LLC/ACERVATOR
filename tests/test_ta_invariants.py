"""The indicator-invariant checker, including its positive controls.

A run that reports "0 violations" is making a claim about the
INSTRUMENT until the instrument is shown capable of reporting a
violation. Half of this file exists to show exactly that: fed the real
historical defects, the checker must say so.

Context. Every `ta.raw.*` record used to emit with no `expected`, so
`Signal.ok` was None and the row was a transcript rather than a check.
ADX ran at up to 761.5 -- seven times its definitional maximum -- across
1174 such rows, and Slingshot reported confidences down to -0.2722.
Neither was flagged, because nothing had been asked to flag them.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading import ta_invariants as ti  # noqa: E402


class TestItCatchesTheDefectsThatActuallyHappened:
    """POSITIVE CONTROLS. Real values from real records."""

    def test_the_inflated_adx(self):
        ok, rule = ti.check("adx", {"adx": 761.52})
        assert ok is False
        assert "adx" in rule

    def test_the_adx_that_was_merely_out_of_range(self):
        """390.9 -- the median-ish reading, not the extreme. A bound
        that only catches the worst case is not a bound."""
        ok, _ = ti.check("adx", {"adx": 390.9})
        assert ok is False

    def test_the_negative_slingshot_confidence(self):
        ok, rule = ti.check("slingshot", {"squeeze_conf": -0.2722})
        assert ok is False
        assert "squeeze_conf" in rule

    def test_the_barely_negative_confidence(self):
        """-0.0038, the smallest real breach. Catching -0.27 but not
        -0.0038 would mean the bound is really a magnitude filter."""
        ok, _ = ti.check("slingshot", {"squeeze_conf": -0.0038})
        assert ok is False


class TestItPassesCorrectValues:
    def test_adx_in_range(self):
        ok, _ = ti.check("adx", {"adx": 27.9, "di_plus": 11.13, "di_minus": 25.94})
        assert ok is True

    def test_adx_at_both_boundaries(self):
        assert ti.check("adx", {"adx": 0.0})[0] is True
        assert ti.check("adx", {"adx": 100.0})[0] is True

    def test_slingshot_at_boundaries(self):
        assert ti.check("slingshot", {"squeeze_conf": 0.0})[0] is True
        assert ti.check("slingshot", {"squeeze_conf": 1.0})[0] is True


class TestFlagInvariantsActuallyEvaluate:
    """`_num` rejects bools on purpose, so a flag invariant routed
    through it would be skipped on every record -- present in the table,
    never evaluated, indistinguishable from passing."""

    def test_exclusive_flags_are_checked_not_skipped(self):
        ok, _ = ti.check(
            "adx", {"ranging": True, "developing": False, "strong_trend": False}
        )
        assert ok is True, "flag invariant was skipped as inapplicable"

    def test_two_regimes_at_once_is_caught(self):
        ok, rule = ti.check(
            "adx", {"ranging": True, "developing": True, "strong_trend": False}
        )
        assert ok is False
        assert "at most one" in rule

    def test_cloud_position_exclusivity(self):
        ok, _ = ti.check(
            "ichimoku",
            {"tk_above_cloud": True, "tk_below_cloud": True, "tk_inside_cloud": False},
        )
        assert ok is False


class TestItDeclinesToJudgeWhatItCannotSee:
    def test_unknown_indicator(self):
        assert ti.check("nonesuch", {"x": 1.0}) == (None, None)

    def test_empty_details_from_warmup(self):
        """Ichimoku returns {} for its first 95 records -- 52 candles of
        warm-up. That must read as UNCHECKED, not as a violation."""
        assert ti.check("ichimoku", {}) == (None, None)

    def test_partial_details(self):
        """Fields absent -> that invariant is skipped, and the ones
        present still evaluate."""
        ok, _ = ti.check("adx", {"adx": 27.9})
        assert ok is True

    def test_non_numeric_value_is_skipped_not_crashed(self):
        assert ti.check("adx", {"adx": None}) == (None, None)
        assert ti.check("adx", {"adx": "27.9"}) == (None, None)

    def test_nan_and_inf_are_not_silently_passed(self):
        assert ti.check("adx", {"adx": float("nan")}) == (None, None)
        assert ti.check("adx", {"adx": float("inf")}) == (None, None)

    def test_a_bool_where_a_number_belongs_is_skipped(self):
        """bool subclasses int, so `0 <= True <= 100` is True. An
        indicator emitting a flag where a magnitude belongs must not
        read as a passing check."""
        assert ti.check("adx", {"adx": True}) == (None, None)


class TestItNeverRaises:
    def test_hostile_inputs(self):
        for bad in (
            None,
            {},
            {"adx": object()},
            {"adx": []},
            {"cloud_top": "x", "cloud_bottom": 1.0},
        ):
            ti.check("adx", bad)
            ti.check("ichimoku", bad)
            ti.check("bollinger_bands", bad)


class TestTheRejectedCandidatesStayRejected:
    """Both were measured against real records and found to fire on
    CORRECT data. If someone re-adds them, these fail."""

    def test_bb_position_above_one_is_legal(self):
        """(price - lower) / (upper - lower) exceeds 1 whenever price
        breaks above the upper band. Seen on 148 of 1181 records."""
        ok, _ = ti.check(
            "bollinger_bands",
            {"bb_position": 1.1324, "lower": 1.0, "middle": 2.0, "upper": 3.0},
        )
        assert ok is not False

    def test_kijun_rising_and_flat_may_coexist(self):
        """`rising` is a sign test, `flat` is a deadband. Any delta
        inside the deadband but above zero satisfies both. Seen on 43
        of 1086 records."""
        ok, _ = ti.check("ichimoku", {"kijun_rising": True, "kijun_flat": True})
        assert ok is not False
