"""ADX must be inside [0, 100], and the gate threshold must track it.

WHAT WAS WRONG. `ADXIndicator._wilder_smooth` documented itself as
"First value = sum/period" and then returned the SUM -- seeded with
`sum(values[:period])`, recursing as `prev - prev/period + v`. Every
output was `period` times Wilder's average.

+DI and -DI divide two of its outputs by each other, so the scale
cancels and they were correct all along. DX does not cancel: it is
already a 0-100 percentage, so ADX came out ~14x its definitional
maximum. Measured on a 3-bot / 400-candle replay of the operator's real
fleet: 1172 of 1174 ADX readings exceeded 100, max 761.5, and the
derived `strong_trend` (>=35) and `parabolic` (>=50) flags were true on
100% of records while `ranging` (<20) could never fire.

WHY IT SURVIVED. v3.20.22 found the inflation and recalibrated
`ADXTrendSuppressionGate.adx_threshold` from 30 to 500 to match the
distorted scale, leaving the indicator wrong. That docstring left an
instruction for whoever fixed it -- reset the threshold to 30 -- so the
two are pinned together here: fixing either one alone yields a gate
that can never fire, or a gate that always fires.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading.ta_engine import ADXIndicator, Candle  # noqa: E402


def _trending(n=300, start=100.0, step=0.6):
    """A clean uptrend -- the regime ADX is meant to score high."""
    out = []
    for i in range(n):
        c = start + i * step
        out.append(Candle(1_700_000_000_000 + i * 300_000,
                          c - step * 0.5, c + step * 0.4,
                          c - step * 0.6, c, 100.0))
    return out


def _choppy(n=300, start=100.0):
    """Oscillation with no net direction -- ADX should read low."""
    out = []
    for i in range(n):
        c = start + math.sin(i / 3.0) * 2.0
        out.append(Candle(1_700_000_000_000 + i * 300_000,
                          c - 0.3, c + 0.5, c - 0.5, c, 100.0))
    return out


class TestADXStaysInsideItsDefinition:
    def test_trending_market_adx_is_bounded(self):
        d = ADXIndicator().compute(_trending()).details
        assert 0.0 <= d["adx"] <= 100.0, d["adx"]

    def test_choppy_market_adx_is_bounded(self):
        d = ADXIndicator().compute(_choppy()).details
        assert 0.0 <= d["adx"] <= 100.0, d["adx"]

    def test_the_bound_can_actually_fail(self):
        """NEGATIVE CONTROL. Re-create the sum-form smoother and show
        it breaches the bound on the same input -- otherwise the two
        assertions above prove nothing about this defect."""
        def sum_form(values, period):
            if len(values) < period:
                return [0.0] * len(values)
            r = [0.0] * (period - 1)
            r.append(sum(values[:period]))
            for v in values[period:]:
                r.append(r[-1] - r[-1] / period + v)
            return r

        ind = ADXIndicator()
        real = ind._wilder_smooth
        try:
            ADXIndicator._wilder_smooth = staticmethod(sum_form)
            broken = ADXIndicator().compute(_trending()).details["adx"]
        finally:
            ADXIndicator._wilder_smooth = staticmethod(real)
        assert broken > 100.0, (
            f"the old smoother should breach the bound, got {broken}")

    def test_di_is_unchanged_by_the_fix(self):
        """+DI/-DI are RATIOS of smoothed values, so dividing both by
        the period cannot move them. If this drifts, the fix changed
        more than it should have."""
        d = ADXIndicator().compute(_trending()).details
        assert 0.0 <= d["di_plus"] <= 100.0
        assert 0.0 <= d["di_minus"] <= 100.0
        assert d["di_plus"] > d["di_minus"], "uptrend must favour +DI"


class TestADXSeparatesRegimes:
    def test_trend_reads_higher_than_chop(self):
        """A bounded value that cannot tell the two apart is bounded
        and useless."""
        t = ADXIndicator().compute(_trending()).details["adx"]
        c = ADXIndicator().compute(_choppy()).details["adx"]
        assert t > c, f"trend {t} should exceed chop {c}"

    def test_textbook_thresholds_are_reachable_both_ways(self):
        t = ADXIndicator().compute(_trending()).details
        c = ADXIndicator().compute(_choppy()).details
        assert t["strong_trend"] is True
        assert c["strong_trend"] is False


class TestTheGateThresholdTracksTheScale:
    def test_threshold_is_the_textbook_value(self):
        from src.trading.gate_chain import ADXTrendSuppressionGate
        assert ADXTrendSuppressionGate().adx_threshold == 30.0

    def test_a_real_trending_adx_can_reach_the_threshold(self):
        """The pairing check. With the old 500.0 default, a correct ADX
        could never trip the gate -- it is bounded at 100."""
        from src.trading.gate_chain import ADXTrendSuppressionGate
        adx = ADXIndicator().compute(_trending()).details["adx"]
        assert adx >= ADXTrendSuppressionGate().adx_threshold
