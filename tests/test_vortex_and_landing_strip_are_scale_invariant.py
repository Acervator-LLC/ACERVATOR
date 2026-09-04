"""VI and bb_position are dimensionless and do not move with price scale.

``VortexIndicator`` divides a directional-movement sum by a true-range sum,
and ``detect_landing_strip_v2`` places a close inside its Bollinger channel.
``SCALES`` renders ``_tape`` at four price bases spanning ten orders of
magnitude, the lowest being the live BONK/USD price.
"""

from __future__ import annotations

import math

import pytest

from src.trading.ta_engine import (
    VortexIndicator,
    candles_from_raw,
    detect_landing_strip_v2,
)

#: Four price bases spanning ten orders of magnitude.
SCALES = (61234.0, 118.0, 0.11, 3.1e-06)

#: A base long enough to fill a 20-bar Bollinger window and a 14-bar Vortex
#: window before the shrinking run starts.
BASE_BARS = 50


def _rows(closes: list[float]) -> list[list[float]]:
    rows: list[list[float]] = []
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        close = closes[i]
        wick = abs(close - prev) * 0.35 + closes[0] * 1.0e-04
        rows.append(
            [
                float(i),
                prev,
                max(prev, close) + wick,
                min(prev, close) - wick,
                close,
                1000.0,
            ]
        )
    return rows


def _tape(base: float, run: int) -> list[list[float]]:
    """A noisy base, then ``run`` rises whose bodies shrink by 0.45 each bar."""
    closes = [base]
    for i in range(1, BASE_BARS):
        closes.append(base + base * 0.002 * math.sin(i * 1.7))
    step = base * 0.01
    for _ in range(run):
        closes.append(closes[-1] + step)
        step *= 0.45
    return _rows(closes)


def _halted(base: float) -> list[list[float]]:
    """Forty identical bars, so every true range is exactly 0.0."""
    return [[float(i), base, base, base, base, 10.0] for i in range(40)]


def _vortex(base: float, run: int = 6):
    return VortexIndicator().compute(candles_from_raw(_tape(base, run)), "1h")


def _strip(base: float, run: int):
    return detect_landing_strip_v2(candles_from_raw(_tape(base, run)), use_ha=False)


def test_vortex_reports_the_same_vi_at_every_price_scale() -> None:
    readings = {base: _vortex(base).details for base in SCALES}
    for field in ("vi_plus", "vi_minus", "separation"):
        values = {base: d[field] for base, d in readings.items()}
        assert len(set(values.values())) == 1, (field, values)


def test_vortex_reports_the_same_direction_at_every_price_scale() -> None:
    directions = {base: _vortex(base).direction for base in SCALES}
    assert len(set(directions.values())) == 1, directions


def test_vortex_reports_the_same_confidence_at_every_price_scale() -> None:
    confidences = {base: _vortex(base).confidence for base in SCALES}
    assert len(set(confidences.values())) == 1, confidences


@pytest.mark.parametrize("base", SCALES)
def test_vortex_reads_two_distinct_lines_on_this_tape(base: float) -> None:
    """The paired control: the equality above compares readings, not zeros."""
    sig = _vortex(base)
    assert sig.abstained is False, base
    assert sig.details["vi_plus"] > 0.0, (base, sig.details)
    assert sig.details["vi_minus"] > 0.0, (base, sig.details)
    assert sig.details["vi_plus"] != sig.details["vi_minus"], (base, sig.details)


@pytest.mark.parametrize("base", SCALES)
def test_vortex_abstains_when_every_true_range_is_zero(base: float) -> None:
    """``window_sums`` carries the whole zero guard, so ``compute`` divides safely."""
    sig = VortexIndicator().compute(candles_from_raw(_halted(base)), "1h")
    assert sig.abstained is True, base
    assert sig.confidence == 0.0, (base, sig.confidence)


def test_landing_strip_reports_the_same_bb_position_at_every_price_scale() -> None:
    positions = {base: _strip(base, 6).bb_position for base in SCALES}
    assert len(set(positions.values())) == 1, positions


@pytest.mark.parametrize("base", SCALES)
def test_landing_strip_measures_a_position_off_the_default(base: float) -> None:
    """The paired control: 0.5 is the value returned before Layer 2 runs."""
    result = _strip(base, 6)
    assert result.raw_tightenings > 0, (base, result)
    assert result.bb_position != 0.5, (base, result.bb_position)


@pytest.mark.parametrize("base", SCALES)
def test_landing_strip_names_the_upper_band_at_every_price_scale(base: float) -> None:
    """The shorter run reaches the band, so ``detected`` is True at every scale."""
    result = _strip(base, 4)
    assert result.detected is True, (base, result)
    assert result.side == "upper", (base, result.side)
