"""Wilder RSI is a ratio of averages and does not move with price scale.

``RSIIndicator`` and ``StochasticRSI`` divide an average gain by an average
loss. ``SCALES`` renders ``PATTERN`` at three price bases spanning nine
orders of magnitude.
"""

from __future__ import annotations

import pytest

from src.trading.ta_engine import (
    RSIIndicator,
    StochasticRSI,
    candles_from_raw,
)
from src.trading.ta_engine import SignalDirection as SD

#: Three price bases spanning nine orders of magnitude.
SCALES = (60000.0, 0.11, 2.0e-05)

#: Four up moves then one down, in units of each scale's own step.
PATTERN = (1.0, 1.0, 1.0, 1.0, -1.0) * 12


def _rows(closes: list[float]) -> list[list[float]]:
    rows: list[list[float]] = []
    prev = closes[0]
    for i, close in enumerate(closes):
        rows.append([float(i), prev, max(prev, close), min(prev, close), close, 500.0])
        prev = close
    return rows


def _scaled(base: float, pattern: tuple[float, ...]) -> list[list[float]]:
    step = base * 1.0e-03
    closes = [base]
    for move in pattern:
        closes.append(closes[-1] + move * step)
    return _rows(closes)


def _monotone(base: float, n: int = 60) -> list[list[float]]:
    step = base * 1.0e-03
    return _rows([base + step * i for i in range(n)])


def test_rsi_reports_the_same_value_at_every_price_scale() -> None:
    readings = {
        base: RSIIndicator().compute(candles_from_raw(_scaled(base, PATTERN)), "1h")
        for base in SCALES
    }
    values = {base: sig.details["rsi"] for base, sig in readings.items()}
    assert len(set(values.values())) == 1, values


def test_rsi_reports_the_same_direction_at_every_price_scale() -> None:
    directions = {
        base: RSIIndicator()
        .compute(candles_from_raw(_scaled(base, PATTERN)), "1h")
        .direction
        for base in SCALES
    }
    assert len(set(directions.values())) == 1, directions


@pytest.mark.parametrize("base", SCALES)
def test_rsi_is_100_when_the_window_has_no_losses(base: float) -> None:
    """``_monotone`` has no down bar, and Wilder RSI at a zero average loss is 100."""
    sig = RSIIndicator().compute(candles_from_raw(_monotone(base)), "1h")
    assert sig.details["rsi"] == 100.0, (base, sig.details["rsi"])
    assert sig.direction is SD.BEARISH, (base, sig.direction)
    assert sig.confidence == 1.0, (base, sig.confidence)


@pytest.mark.parametrize("base", SCALES)
def test_rsi_is_below_100_when_the_window_has_losses(base: float) -> None:
    """The paired control on ``_scaled``: 100.0 is a reading, not a constant."""
    sig = RSIIndicator().compute(candles_from_raw(_scaled(base, PATTERN)), "1h")
    assert 0.0 < sig.details["rsi"] < 100.0, (base, sig.details["rsi"])


@pytest.mark.parametrize("base", SCALES)
def test_stochastic_rsi_abstains_on_a_monotone_tape_at_every_scale(
    base: float,
) -> None:
    """``_monotone`` pins RSI at 100, leaving the ``stoch_period`` window flat."""
    sig = StochasticRSI().compute(candles_from_raw(_monotone(base, 120)), "1h")
    assert sig.direction is SD.NEUTRAL, (base, sig.direction)
    assert sig.confidence == 0.0, (base, sig.confidence)


def test_stochastic_rsi_votes_on_a_tape_that_has_losses() -> None:
    """The paired control: ``StochasticRSI`` votes on a tape that has losses."""
    rows = _scaled(60000.0, (1.0, 1.0, -1.0, 1.0, -1.0, -1.0, 1.0) * 20)
    sig = StochasticRSI().compute(candles_from_raw(rows), "1h")
    assert sig.details is not None
    assert sig.details["k"] is not None
