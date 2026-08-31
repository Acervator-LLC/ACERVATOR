"""A volatility flag must not depend on the asset's price.

WHAT WAS WRONG. `BollingerBands.compute` built

    band_width = (upper - lower) / (mid + 1e-9)          # DIMENSIONLESS
    widths     = [(sma[i] + k*std[i]) - (sma[i] - k*std[i]) ...]
    squeeze    = band_width < avg(widths) * 0.75

The `sma[i]` terms in `widths` cancel exactly, leaving `2*k*std[i]` in
PRICE UNITS. The comparison therefore put a ratio against an absolute
width. Setting sigma ~ sigma_avg it reduces to `mid > 1.33`: an asset
cheaper than about $1.33 could never register a squeeze, and a dearer
one almost always could.

MEASURED with the production class on real Stone Tablets across all 35
live fleet symbols, 334 windows each. BEFORE: every one of the 21
symbols at or below $0.42 squeezed on 0.0% of windows; every one of the
6 at or above $8.28 squeezed on 100.0%; the transition ran monotonically
through SUI $0.69 (4.5%), XRP $1.07 (29.9%), ORCA $1.17 (36.8%), NEAR
$1.65 (77.2%). AFTER: every symbol lands in 17.7-29.6%, with BONK at
$0.0000045 and BTC at $63,787 both near 25%.

It reached trading -- `confidence *= 0.7` fires only when squeezed, so
the damping was being applied on the basis of price.

The correct form already existed in this repo at
`native_chart.py`'s `CandlestickChart.paintEvent`, which averages
bandwidth and compares
bandwidth. The chart drew squeezes the engine could not see.

THE TEST IS SCALE INVARIANCE. That is the definitional property: a
squeeze is about the shape of a series, and multiplying every price by
a positive constant does not change its shape.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading.ta_engine import BollingerBands, Candle  # noqa: E402

SCALES = (0.001, 0.03, 0.08, 1.44, 100.0, 65_000.0)


def _series(scale, n=120, seed=7):
    """A deterministic walk with a contraction then an expansion, so
    both squeeze states occur somewhere in the series."""
    out, px, rnd = [], 1.0, seed
    for i in range(n):
        rnd = (rnd * 1103515245 + 12345) % 2147483648
        amp = 0.02 if 40 <= i < 80 else 0.12  # contract, expand
        px *= 1.0 + ((rnd / 2147483648) - 0.5) * amp
        c = px * scale
        out.append(
            Candle(1_700_000_000_000 + i * 300_000, c, c * 1.002, c * 0.998, c, 100.0)
        )
    return out


def _squeeze_at(scale, n=120):
    return BollingerBands().compute(_series(scale, n)).details["squeeze"]


class TestSqueezeDoesNotDependOnPrice:
    def test_same_series_every_scale_agrees(self):
        verdicts = {s: _squeeze_at(s) for s in SCALES}
        assert (
            len(set(verdicts.values())) == 1
        ), f"squeeze changed with price scale: {verdicts}"

    def test_band_width_is_scale_invariant_too(self):
        """The quantity the flag is built on."""
        widths = [
            BollingerBands().compute(_series(s)).details["band_width"] for s in SCALES
        ]
        assert max(widths) - min(widths) < 1e-6, widths

    def test_across_many_windows(self):
        """One window agreeing could be luck. Every prefix must agree."""
        for n in range(60, 121, 10):
            verdicts = {s: _squeeze_at(s, n) for s in SCALES}
            assert len(set(verdicts.values())) == 1, (n, verdicts)


class TestTheOldFormWasNotScaleInvariant:
    """NEGATIVE CONTROL. Recompute both forms directly and show the old
    one flips with price while the new one does not -- otherwise the
    tests above could pass on an indicator that ignores squeeze."""

    @staticmethod
    def _both(scale, period=20, k=2.0):
        closes = [c.close for c in _series(scale)]
        sma, std = [], []
        for i in range(period - 1, len(closes)):
            w = closes[i - period + 1 : i + 1]
            m = sum(w) / period
            sma.append(m)
            std.append(math.sqrt(sum((x - m) ** 2 for x in w) / period))
        mid = sma[-1]
        band_width = (mid + k * std[-1] - (mid - k * std[-1])) / (mid + 1e-9)
        absolute = [2 * k * s for s in std[-period:]]
        relative = [
            2 * k * s / (m + 1e-9) for s, m in zip(std[-period:], sma[-period:])
        ]
        return (
            band_width < sum(absolute) / period * 0.75,
            band_width < sum(relative) / period * 0.75,
        )

    def test_old_form_flips_with_scale(self):
        old = {s: self._both(s)[0] for s in SCALES}
        assert (
            len(set(old.values())) > 1
        ), f"the units bug should flip with scale, got {old}"

    def test_new_form_holds_across_scale(self):
        new = {s: self._both(s)[1] for s in SCALES}
        assert len(set(new.values())) == 1, new

    def test_cheap_assets_could_never_squeeze_under_the_old_form(self):
        """The specific shape of the defect: sub-$1.33 assets pinned
        False. CHIP was $0.08 and SPK $0.03."""
        assert self._both(0.03)[0] is False
        assert self._both(0.08)[0] is False
