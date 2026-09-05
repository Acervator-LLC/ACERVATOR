"""MACD confidence and Kaufman's ER do not move with price scale.

``MACD.compute`` divides a histogram by a fraction of the last close, and
``KaufmanERIndicator.compute`` divides a net price change by the distance
travelled. ``SCALES`` renders ``_tape`` at four price bases spanning ten
orders of magnitude, the lowest being the live BONK/USD price.
"""

from __future__ import annotations

import math

import pytest

from src.trading.ta_engine import (
    KaufmanERIndicator,
    MACD,
    candles_from_raw,
)

#: Four price bases spanning ten orders of magnitude.
SCALES = (61234.0, 118.0, 0.11, 3.1e-06)

#: Long enough to clear MACD's ``slow + signal`` warm-up of 35 bars.
BASE_BARS = 60

#: The slope that puts ``er`` just above the 0.50 ``trending`` threshold.
TRENDING_SLOPE = 0.00034

#: A slope below the ``trending`` threshold at every scale.
RANGING_SLOPE = 0.0002


def _tape(base: float, amplitude: float, slope: float) -> list[list[float]]:
    """Build a drift of ``slope`` per bar with an oscillation of ``amplitude``."""
    closes = [base]
    for i in range(1, BASE_BARS):
        closes.append(base + base * slope * i + base * amplitude * math.sin(i * 1.9))
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


def _kaufman(base: float, slope: float):
    return KaufmanERIndicator().compute(
        candles_from_raw(_tape(base, 0.0006, slope)), "1h"
    )


def _macd(base: float):
    return MACD().compute(candles_from_raw(_tape(base, 0.003, 0.0003)), "1h")


def test_kaufman_er_reports_the_same_ratio_at_every_price_scale() -> None:
    ratios = {base: _kaufman(base, TRENDING_SLOPE).details["er"] for base in SCALES}
    assert len(set(ratios.values())) == 1, ratios


def test_kaufman_er_reports_the_same_direction_at_every_price_scale() -> None:
    """The BONK reading crossed 0.50 downward while the others did not."""
    verdicts = {base: _kaufman(base, TRENDING_SLOPE).direction for base in SCALES}
    assert len(set(verdicts.values())) == 1, verdicts


def test_kaufman_er_reports_the_same_trending_band_at_every_price_scale() -> None:
    bands = {
        base: _kaufman(base, TRENDING_SLOPE).details["trending"] for base in SCALES
    }
    assert len(set(bands.values())) == 1, bands


def test_kaufman_er_reports_the_same_confidence_at_every_price_scale() -> None:
    scores = {base: _kaufman(base, TRENDING_SLOPE).confidence for base in SCALES}
    reference = scores[SCALES[0]]
    for base, score in scores.items():
        assert score == pytest.approx(reference, rel=1e-12), (base, scores)


@pytest.mark.parametrize("base", SCALES)
def test_kaufman_er_measures_a_ratio_strictly_inside_its_range(base: float) -> None:
    """The paired control: the equalities above compare readings, not zeros."""
    signal = _kaufman(base, TRENDING_SLOPE)
    assert signal.abstained is False, base
    assert 0.0 < signal.details["er"] < 1.0, (base, signal.details)
    assert signal.confidence > 0.0, (base, signal.confidence)


@pytest.mark.parametrize("base", SCALES)
def test_kaufman_er_separates_a_ranging_tape_from_a_trending_one(base: float) -> None:
    """The second control: the ratio answers the tape, not the fixture."""
    ranging = _kaufman(base, RANGING_SLOPE)
    trending = _kaufman(base, TRENDING_SLOPE)
    assert ranging.details["trending"] is False, (base, ranging.details)
    assert trending.details["trending"] is True, (base, trending.details)
    assert ranging.details["er"] < trending.details["er"], (base, ranging.details)


def test_macd_reports_the_same_confidence_at_every_price_scale() -> None:
    scores = {base: _macd(base).confidence for base in SCALES}
    reference = scores[SCALES[0]]
    for base, score in scores.items():
        assert score == pytest.approx(reference, rel=1e-12), (base, scores)


def test_macd_reports_the_same_direction_at_every_price_scale() -> None:
    verdicts = {base: _macd(base).direction for base in SCALES}
    assert len(set(verdicts.values())) == 1, verdicts


@pytest.mark.parametrize("base", SCALES)
def test_macd_measures_a_confidence_off_both_of_its_clamps(base: float) -> None:
    """The paired control: 0.5 is the crossover floor and 1.0 is the ceiling."""
    signal = _macd(base)
    assert signal.abstained is False, base
    assert signal.details["crossover"] is True, (base, signal.details)
    assert 0.5 < signal.confidence < 1.0, (base, signal.confidence)
