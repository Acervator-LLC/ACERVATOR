"""``bb_position`` and the Slingshot ratios do not move with price scale.

``BollingerBands.compute`` places a close inside its own channel and
``SlingshotIndicator.compute`` divides momentum by a Keltner range, and
neither quotient carries a price unit. ``SCALES`` renders each ``SHAPES``
tape at four bases, the lowest being the live BONK/USD price.
"""

from __future__ import annotations

import math

import pytest

from src.trading.ta_engine import (
    BollingerBands,
    SlingshotIndicator,
    candles_from_raw,
)

#: Four price bases spanning ten orders of magnitude.
SCALES = (61234.0, 118.0, 0.11, 3.1e-06)

#: ``BollingerBands`` detail fields quoted in dollars.
PRICED_BB = ("upper", "middle", "lower")

#: ``SlingshotIndicator`` detail fields quoted in dollars.
PRICED_SL = ("momentum", "fire_momentum")

#: Slack from rendering one shape at four bases in binary floats.
CONF_SPREAD = 1e-11

#: A spread this wide is the epsilon; ``CONF_SPREAD`` bounds the rendering.
EPSILON_SPREAD = 1e-6


def _rows(closes: list[float]) -> list[list[float]]:
    rows: list[list[float]] = []
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        close = closes[i]
        wick = abs(close - prev) * 0.35 + 1.0e-04
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


def _ramp(bars: int = 50, run: int = 6) -> list[list[float]]:
    """A noisy base, then ``run`` rises whose bodies shrink by 0.45 each bar."""
    closes = [1.0]
    for i in range(1, bars):
        closes.append(1.0 + 0.002 * math.sin(i * 1.7))
    step = 0.01
    for _ in range(run):
        closes.append(closes[-1] + step)
        step *= 0.45
    return _rows(closes)


def _squeeze(n: int = 160, seed: int = 7) -> list[list[float]]:
    """A wide walk, a quiet middle, then a wide walk again."""
    price, state = 1.0, seed
    closes = []
    for i in range(n):
        state = (state * 1103515245 + 12345) % 2147483648
        amp = 0.015 if 55 <= i < 110 else 0.10
        price *= 1.0 + ((state / 2147483648) - 0.5) * amp
        closes.append(price)
    return _rows(closes)


def _snapback(n: int = 90, seed: int = 3) -> list[list[float]]:
    """A quiet walk, one close 10% below it, then three closes back inside."""
    price, state = 1.0, seed
    closes = []
    for _ in range(n):
        state = (state * 1103515245 + 12345) % 2147483648
        price *= 1.0 + ((state / 2147483648) - 0.5) * 0.010
        closes.append(price)
    closes[-4] = closes[-5] * 0.90
    closes[-3] = closes[-5] * 0.995
    closes[-2] = closes[-5] * 1.000
    closes[-1] = closes[-5] * 1.004
    return _rows(closes)


SHAPES = {"ramp": _ramp(), "squeeze": _squeeze(), "snapback": _snapback()}


def _scaled(shape: list[list[float]], base: float) -> list[list[float]]:
    return [[r[0], *(px * base for px in r[1:5]), r[5]] for r in shape]


def _halted(base: float, bars: int = 60) -> list[list[float]]:
    """Sixty identical bars, so the whole window has no range."""
    return [[float(i), base, base, base, base, 10.0] for i in range(bars)]


def _bb(shape: str, base: float):
    return BollingerBands().compute(candles_from_raw(_scaled(SHAPES[shape], base)))


def _sl(shape: str, base: float):
    return SlingshotIndicator().compute(candles_from_raw(_scaled(SHAPES[shape], base)))


def _spread(values) -> float:
    return max(values) - min(values)


# ── Bollinger ────────────────────────────────────────────────────────
@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_bollinger_details_move_only_in_the_priced_fields(shape: str) -> None:
    readings = {base: _bb(shape, base).details for base in SCALES}
    for field in sorted(readings[SCALES[0]]):
        values = {base: d[field] for base, d in readings.items()}
        if field in PRICED_BB:
            assert len(set(values.values())) == len(SCALES), (field, values)
        else:
            assert len(set(map(repr, values.values()))) == 1, (field, values)


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_bollinger_votes_the_same_direction_at_every_price_scale(shape: str) -> None:
    directions = {base: _bb(shape, base).direction for base in SCALES}
    assert len(set(directions.values())) == 1, directions


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_bollinger_confidence_holds_across_price_scale(shape: str) -> None:
    confidences = {base: _bb(shape, base).confidence for base in SCALES}
    assert _spread(confidences.values()) < CONF_SPREAD, confidences


def test_bollinger_measures_a_live_band_position_on_the_ramp_tape() -> None:
    """The paired control: the ramp reaches the ``bb_pos > 0.85`` branch."""
    for base in SCALES:
        sig = _bb("ramp", base)
        assert sig.abstained is False, base
        assert sig.details["bb_position"] > 0.85, (base, sig.details)
        assert sig.confidence > 0.3, (base, sig.confidence)


@pytest.mark.parametrize("base", SCALES)
def test_bollinger_abstains_when_the_window_has_no_range(base: float) -> None:
    """``_window_has_no_range`` carries the zero, not an epsilon."""
    sig = BollingerBands().compute(candles_from_raw(_halted(base)))
    assert sig.abstained is True, base
    assert sig.confidence == 0.0, (base, sig.confidence)


# ── Slingshot ────────────────────────────────────────────────────────
@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_slingshot_details_move_only_in_the_priced_fields(shape: str) -> None:
    readings = {base: _sl(shape, base).details for base in SCALES}
    for field in sorted(readings[SCALES[0]]):
        values = {base: d[field] for base, d in readings.items()}
        if field in PRICED_SL:
            continue
        assert len(set(map(repr, values.values()))) == 1, (field, values)


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_slingshot_votes_the_same_direction_at_every_price_scale(shape: str) -> None:
    directions = {base: _sl(shape, base).direction for base in SCALES}
    assert len(set(directions.values())) == 1, directions


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_slingshot_confidence_holds_across_price_scale(shape: str) -> None:
    confidences = {base: _sl(shape, base).confidence for base in SCALES}
    assert _spread(confidences.values()) < CONF_SPREAD, confidences


def test_slingshot_fires_a_squeeze_release_on_the_ramp_tape() -> None:
    """The paired control for ``mom_norm``: a fire, not a default zero."""
    for base in SCALES:
        sig = _sl("ramp", base)
        assert sig.abstained is False, base
        assert sig.details["bars_since_fire"] >= 0, (base, sig.details)
        assert sig.details["mom_norm"] > 0.0, (base, sig.details)


def test_slingshot_reads_a_band_snapback_on_the_snapback_tape() -> None:
    """The paired control for ``penetration``: a break and a re-entry."""
    for base in SCALES:
        sig = _sl("snapback", base)
        assert sig.details["snapback_type"] == "bullish_snapback", (base, sig.details)
        assert sig.details["snapback_conf"] > 0.35, (base, sig.details)


@pytest.mark.parametrize("base", SCALES)
def test_slingshot_abstains_when_the_window_has_no_range(base: float) -> None:
    """``_window_has_no_range`` carries the zero, not an epsilon."""
    sig = SlingshotIndicator().compute(candles_from_raw(_halted(base)))
    assert sig.abstained is True, base
    assert sig.confidence == 0.0, (base, sig.confidence)


# ── the negative controls ────────────────────────────────────────────
def test_an_absolute_epsilon_moves_bb_position_with_price_scale() -> None:
    """Drive the real bands through ``upper - lower + 1e-9`` and watch it slide."""
    positions = {}
    for base in SCALES:
        candles = candles_from_raw(_scaled(SHAPES["ramp"], base))
        upper, _middle, lower = BollingerBands().bands(candles)[-1]
        positions[base] = (candles[-1].close - lower) / (upper - lower + 1e-9)
    assert _spread(positions.values()) > EPSILON_SPREAD, positions


def test_an_absolute_epsilon_moves_bandwidth_with_price_scale() -> None:
    """The same term against ``SlingshotIndicator._bandwidth``'s own denominator."""
    shipped, epsilon = {}, {}
    for base in SCALES:
        candles = candles_from_raw(_scaled(SHAPES["ramp"], base))
        upper, middle, lower = BollingerBands().bands(candles)[-1]
        shipped[base] = SlingshotIndicator._bandwidth(upper, lower, middle)
        epsilon[base] = (upper - lower) / (middle + 1e-9)
    assert _spread(shipped.values()) < CONF_SPREAD, shipped
    assert _spread(epsilon.values()) > EPSILON_SPREAD, epsilon
