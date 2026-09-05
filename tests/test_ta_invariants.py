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


class TestARaisingPredicateIsNotCountedAsChecked:
    """`check` counts an `Invariant` only after its predicate returns."""

    @staticmethod
    def _exploding(_details):
        raise ZeroDivisionError("predicate read a field outside Invariant.fields")

    def _install(self, monkeypatch, name, invariants):
        table = dict(ti.INDICATORS)
        table[name] = invariants
        monkeypatch.setattr(ti, "INDICATORS", table)

    def test_an_indicator_whose_only_bound_raises_reads_as_unchecked(self, monkeypatch):
        self._install(
            monkeypatch,
            "probe",
            (ti.Invariant(("x",), "x >= 0", self._exploding),),
        )
        assert ti.check("probe", {"x": 1.0}) == (
            None,
            None,
        ), "a bound that never evaluated must not read as a passing check"

    def test_the_count_names_only_the_bounds_that_evaluated(self, monkeypatch):
        self._install(
            monkeypatch,
            "probe",
            (
                ti.Invariant(("x",), "x >= 0", self._exploding),
                ti.Invariant(("x",), "x <= 10", lambda d: float(d["x"]) <= 10.0),
            ),
        )
        ok, rule = ti.check("probe", {"x": 1.0})
        assert (ok, rule) == (True, "1 invariants"), (ok, rule)

    def test_a_working_pair_still_counts_two(self, monkeypatch):
        """Positive control: with no raise, both bounds count."""
        self._install(
            monkeypatch,
            "probe",
            (
                ti.Invariant(("x",), "x >= 0", lambda d: float(d["x"]) >= 0.0),
                ti.Invariant(("x",), "x <= 10", lambda d: float(d["x"]) <= 10.0),
            ),
        )
        assert ti.check("probe", {"x": 1.0}) == (True, "2 invariants")


class TestEveryDeclaredBoundEvaluates:
    """A bound present in `INDICATORS` but never applied is invisible."""

    FULL_DETAILS = {
        "rsi": {"rsi": 50.0},
        "stochastic_rsi": {"k": 50.0, "d": 40.0},
        "adx": {
            "adx": 25.0,
            "di_plus": 20.0,
            "di_minus": 15.0,
            "ranging": False,
            "developing": True,
            "strong_trend": False,
            "bull_dominant": True,
            "bear_dominant": False,
            "di_bull_cross": False,
            "di_bear_cross": True,
        },
        "bollinger_bands": {
            "lower": 9.0,
            "middle": 10.0,
            "upper": 11.0,
            "band_width": 2.0,
        },
        "zscore": {"std": 1.5},
        "kaufman_er": {"er": 0.5},
        "vortex": {"vi_plus": 1.1, "vi_minus": 0.9},
        "volume": {
            "mfi": 55.0,
            "cmf": 0.2,
            "mfi_overbought": False,
            "mfi_oversold": True,
            "cmf_bull": True,
            "cmf_bear": False,
        },
        "supertrend": {
            "curr_atr": 12.0,
            "dist_pct": 3.0,
            "flip_bull": True,
            "flip_bear": False,
        },
        "ichimoku": {
            "cloud_top": 110.0,
            "cloud_bottom": 100.0,
            "cloud_thick_pct": 9.0,
            "tk_above_cloud": True,
            "tk_inside_cloud": False,
            "tk_below_cloud": False,
            "tk_bull_cross": True,
            "tk_bear_cross": False,
            "twist_to_bull": False,
            "twist_to_bear": True,
            "chikou_bull": True,
            "chikou_bear": False,
            "breakout_up": False,
            "breakout_down": True,
            "san_ko_shu_bull": True,
            "san_ko_shu_bear": False,
        },
        "slingshot": {
            "squeeze_conf": 0.6,
            "snapback_conf": 0.4,
            "curr_bw": 0.02,
            "avg_bw": 0.03,
            "squeeze_bull": True,
            "squeeze_bear": False,
        },
        "macd": {"macd_line": 1.5, "signal_line": 1.0, "histogram": 0.5},
    }

    def test_every_indicator_in_the_table_has_a_full_details_case(self):
        assert set(self.FULL_DETAILS) == set(ti.INDICATORS)

    def test_a_full_details_dict_applies_every_declared_bound(self):
        for indicator, details in self.FULL_DETAILS.items():
            declared = len(ti.invariants_for(indicator))
            ok, rule = ti.check(indicator, details)
            assert (ok, rule) == (True, f"{declared} invariants"), (
                indicator,
                declared,
                ok,
                rule,
            )


BREACHES = {
    "0 <= rsi <= 100": {"rsi": 761.52},
    "0 <= k <= 100": {"k": 140.0},
    "0 <= d <= 100": {"d": -1.0},
    "0 <= adx <= 100": {"adx": 761.52},
    "0 <= di_plus <= 100": {"di_plus": 140.0},
    "0 <= di_minus <= 100": {"di_minus": -1.0},
    "at most one of: ranging, developing, strong_trend": {"ranging": True},
    "at most one of: bull_dominant, bear_dominant": {"bear_dominant": True},
    "at most one of: di_bull_cross, di_bear_cross": {"di_bull_cross": True},
    "lower <= middle <= upper": {"lower": 12.0},
    "band_width >= 0": {"band_width": -1.0},
    "std >= 0": {"std": -1e-9},
    "0 <= er <= 1": {"er": 1.5},
    "vi_plus >= 0": {"vi_plus": -0.5},
    "vi_minus >= 0": {"vi_minus": -0.5},
    "0 <= mfi <= 100": {"mfi": 140.0},
    "-1 <= cmf <= 1": {"cmf": -1.5},
    "at most one of: mfi_overbought, mfi_oversold": {"mfi_overbought": True},
    "at most one of: cmf_bull, cmf_bear": {"cmf_bear": True},
    "curr_atr >= 0": {"curr_atr": -1.0},
    "dist_pct >= 0": {"dist_pct": -46.37},
    "at most one of: flip_bull, flip_bear": {"flip_bear": True},
    "cloud_bottom <= cloud_top": {"cloud_bottom": 120.0},
    "cloud_thick_pct >= 0": {"cloud_thick_pct": -0.001},
    "at most one of: tk_above_cloud, tk_inside_cloud, tk_below_cloud": {
        "tk_below_cloud": True
    },
    "at most one of: tk_bull_cross, tk_bear_cross": {"tk_bear_cross": True},
    "at most one of: twist_to_bull, twist_to_bear": {"twist_to_bull": True},
    "at most one of: chikou_bull, chikou_bear": {"chikou_bear": True},
    "at most one of: breakout_up, breakout_down": {"breakout_up": True},
    "at most one of: san_ko_shu_bull, san_ko_shu_bear": {"san_ko_shu_bear": True},
    "0 <= squeeze_conf <= 1": {"squeeze_conf": -0.2722},
    "0 <= snapback_conf <= 1": {"snapback_conf": 1.5},
    "curr_bw >= 0": {"curr_bw": -1e-6},
    "avg_bw >= 0": {"avg_bw": -1e-6},
    "at most one of: squeeze_bull, squeeze_bear": {"squeeze_bear": True},
    "histogram == macd_line - signal_line": {"histogram": 0.501},
}


class TestEveryDeclaredBoundCanReportABreach:
    """A breaching value must make `check` name that bound's rule."""

    def test_a_breach_is_written_for_every_rule_in_the_table(self):
        declared = {inv.rule for invs in ti.INDICATORS.values() for inv in invs}
        assert declared == set(BREACHES)

    def test_each_bound_names_itself_when_breached(self):
        for indicator, good in TestEveryDeclaredBoundEvaluates.FULL_DETAILS.items():
            for inv in ti.invariants_for(indicator):
                details = dict(good)
                details.update(BREACHES[inv.rule])
                ok, rule = ti.check(indicator, details)
                assert (ok, rule) == (False, inv.rule), (
                    indicator,
                    inv.rule,
                    ok,
                    rule,
                )


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
