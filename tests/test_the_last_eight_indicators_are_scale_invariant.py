"""The last eight indicators do not move with price or volume scale.

``ADXIndicator``, ``detect_bb_proximity``, ``compute_heikin_ashi``,
``IchimokuCloud``, ``StochasticRSI``, ``SupertrendIndicator``,
``VolumeAnalysis`` and ``ZScoreIndicator`` each divide by a quantity that
carries a unit. ``SCALES`` renders every ``SHAPES`` tape at four price
bases, the lowest the live BONK/USD price, and ``VOLUME_FACTORS`` does the
same to ``VolumeAnalysis``.
"""

from __future__ import annotations

import math

import pytest

from src.trading.ta_engine import (
    ADXIndicator,
    IchimokuCloud,
    StochasticRSI,
    SupertrendIndicator,
    VolumeAnalysis,
    ZScoreIndicator,
    candles_from_raw,
    compute_heikin_ashi,
    detect_bb_proximity,
)

#: Four price bases spanning ten orders of magnitude.
SCALES = (61234.0, 118.0, 0.11, 3.1e-06)

#: Four volume multipliers; ``VolumeAnalysis`` divides by a volume mean.
VOLUME_FACTORS = (1.0, 1e-4, 1e3, 1e7)

#: Detail fields quoted in dollars, per indicator.
PRICED = {
    "adx": (),
    "ichimoku": ("cloud_top", "cloud_bottom", "tenkan", "kijun"),
    "stochastic_rsi": (),
    "supertrend": ("st_line", "curr_atr"),
    "volume": (),
    "zscore": ("sma", "std", "resistance_price", "support_price"),
}

#: Slack from rendering one shape at four bases in binary floats.
CONF_SPREAD = 1e-11

#: A spread this wide is the epsilon; ``CONF_SPREAD`` bounds the rendering.
EPSILON_SPREAD = 1e-6


def _rows(closes: list[float], volume: float = 1000.0) -> list[list[float]]:
    rows: list[list[float]] = []
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        close = closes[i]
        floor = min(prev, close)
        wick = min(abs(close - prev) * 0.35, floor * 0.1) + floor * 1e-4
        rows.append(
            [
                float(i),
                prev,
                max(prev, close) + wick,
                min(prev, close) - wick,
                close,
                volume,
            ]
        )
    return rows


def _walk(bars: int, seed: int, amp: float) -> list[float]:
    price, state = 1.0, seed
    closes = []
    for _ in range(bars):
        state = (state * 1103515245 + 12345) % 2147483648
        price *= 1.0 + ((state / 2147483648) - 0.5) * amp
        closes.append(price)
    return closes


def _ramp(bars: int = 200, run: int = 6) -> list[list[float]]:
    """A noisy base, then ``run`` rises whose bodies shrink by 0.45 each bar."""
    closes = [1.0]
    for i in range(1, bars):
        closes.append(1.0 + 0.002 * math.sin(i * 1.7))
    step = 0.01
    for _ in range(run):
        closes.append(closes[-1] + step)
        step *= 0.45
    return _rows(closes)


def _squeeze(bars: int = 200, seed: int = 7) -> list[list[float]]:
    """A wide walk, a quiet middle, then a wide walk again."""
    price, state = 1.0, seed
    closes = []
    for i in range(bars):
        state = (state * 1103515245 + 12345) % 2147483648
        amp = 0.015 if 70 <= i < 140 else 0.10
        price *= 1.0 + ((state / 2147483648) - 0.5) * amp
        closes.append(price)
    return _rows(closes)


def _trend_down(bars: int = 200, seed: int = 13) -> list[list[float]]:
    """A quiet walk carried downward by 0.3% a bar."""
    closes = _walk(bars, seed, 0.004)
    return _rows([c * (1.0 - 0.003 * i) for i, c in enumerate(closes)])


def _tight(bars: int = 200, seed: int = 37) -> list[list[float]]:
    """A walk whose dispersion is a few parts in 100,000 of the price."""
    return _rows(_walk(bars, seed, 0.00006))


def _halt(bars: int = 200, seed: int = 23) -> list[list[float]]:
    """A walk, then fifty bars with no range at all."""
    closes = _walk(bars, seed, 0.008)
    for i in range(150, bars):
        closes[i] = closes[149]
    rows = _rows(closes)
    for row in rows[150:]:
        row[1] = row[2] = row[3] = row[4]
    return rows


def _thin(bars: int = 200, seed: int = 41) -> list[list[float]]:
    """A walk whose bars trade a billionth of a unit."""
    rows = _rows(_walk(bars, seed, 0.008))
    for i, row in enumerate(rows):
        row[5] = 1e-9 * (1.0 + 0.4 * (i % 5))
    return rows


SHAPES = {
    "ramp": _ramp(),
    "squeeze": _squeeze(),
    "trend_down": _trend_down(),
    "tight": _tight(),
    "halt": _halt(),
    "thin": _thin(),
}


def _scaled(shape: list[list[float]], base: float) -> list[list[float]]:
    return [[r[0], *(px * base for px in r[1:5]), r[5]] for r in shape]


def _vol_scaled(shape: list[list[float]], factor: float) -> list[list[float]]:
    return [[*r[:5], r[5] * factor] for r in shape]


def _flat(base: float, bars: int = 200) -> list[list[float]]:
    """Every bar the same price, so the whole window has no range."""
    return [[float(i), base, base, base, base, 10.0] for i in range(bars)]


def _signal(name: str, rows: list[list[float]]):
    candles = candles_from_raw(rows)
    return {
        "adx": ADXIndicator().compute,
        "ichimoku": IchimokuCloud().compute,
        "stochastic_rsi": StochasticRSI().compute,
        "supertrend": SupertrendIndicator().compute,
        "volume": VolumeAnalysis().compute,
        "zscore": ZScoreIndicator().compute,
    }[name](candles)


def _spread(values) -> float:
    return max(values) - min(values)


VOTERS = sorted(PRICED)
CASES = [(name, shape) for name in VOTERS for shape in sorted(SHAPES)]


# ── the six voters ───────────────────────────────────────────────────
@pytest.mark.parametrize(("name", "shape"), CASES)
def test_details_move_only_in_the_priced_fields(name: str, shape: str) -> None:
    readings = {
        base: _signal(name, _scaled(SHAPES[shape], base)).details or {}
        for base in SCALES
    }
    for field in sorted(readings[SCALES[0]]):
        values = {base: d.get(field) for base, d in readings.items()}
        if field in PRICED[name]:
            continue
        assert len(set(map(repr, values.values()))) == 1, (name, field, values)


@pytest.mark.parametrize(("name", "shape"), CASES)
def test_a_voter_reads_the_same_direction_at_every_price_scale(
    name: str, shape: str
) -> None:
    directions = {
        base: _signal(name, _scaled(SHAPES[shape], base)).direction for base in SCALES
    }
    assert len(set(directions.values())) == 1, (name, directions)


@pytest.mark.parametrize(("name", "shape"), CASES)
def test_a_voter_holds_its_confidence_across_price_scale(name: str, shape: str) -> None:
    confidences = {
        base: _signal(name, _scaled(SHAPES[shape], base)).confidence for base in SCALES
    }
    assert _spread(confidences.values()) < CONF_SPREAD, (name, confidences)


@pytest.mark.parametrize(("name", "shape"), CASES)
def test_a_voter_abstains_or_reads_the_same_way_at_every_price_scale(
    name: str, shape: str
) -> None:
    abstained = {
        base: _signal(name, _scaled(SHAPES[shape], base)).abstained for base in SCALES
    }
    assert len(set(abstained.values())) == 1, (name, abstained)


# ── the two that return no Signal ────────────────────────────────────
@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_bb_proximity_moves_only_in_its_priced_fields(shape: str) -> None:
    priced = {"upper", "middle", "lower"}
    readings = {
        base: detect_bb_proximity(candles_from_raw(_scaled(SHAPES[shape], base)))
        for base in SCALES
    }
    for field in readings[SCALES[0]].__dataclass_fields__:
        if field in priced:
            continue
        values = {base: getattr(r, field) for base, r in readings.items()}
        assert len(set(map(repr, values.values()))) == 1, (field, values)


def _bodies(shape: str, base: float) -> list[float]:
    rows = _scaled(SHAPES[shape], base)
    return [c.body_pct for c in compute_heikin_ashi(candles_from_raw(rows))[-40:]]


@pytest.mark.parametrize("shape", sorted(set(SHAPES) - {"halt"}))
def test_heikin_ashi_body_pct_holds_across_price_scale(shape: str) -> None:
    bodies = {base: _bodies(shape, base) for base in SCALES}
    reference = bodies[SCALES[0]]
    for base in SCALES[1:]:
        for i, (want, got) in enumerate(zip(reference, bodies[base])):
            assert abs(got - want) <= 1e-9 * max(1.0, abs(want)), (base, i, want, got)


def test_a_halted_bar_carries_no_tight_body_at_any_price_scale() -> None:
    """``hl_range`` reaches zero through ``ha_open`` converging on ``ha_close``.

    A bar that answers ``math.nan`` at one base answers a full-range body at
    another, and ``detect_bb_proximity`` ends its run on either.
    """
    tight = 3.0
    for base in SCALES:
        for body in _bodies("halt", base):
            assert math.isnan(body) or body > tight, (base, body)


# ── volume carries a volume unit, not a price ────────────────────────
@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_volume_details_hold_across_volume_scale(shape: str) -> None:
    readings = {
        factor: VolumeAnalysis()
        .compute(candles_from_raw(_vol_scaled(SHAPES[shape], factor)))
        .details
        or {}
        for factor in VOLUME_FACTORS
    }
    for field in sorted(readings[VOLUME_FACTORS[0]]):
        values = {f: d.get(field) for f, d in readings.items()}
        assert len(set(map(repr, values.values()))) == 1, (field, values)


# ── the paired controls: these tapes carry real readings ─────────────
def test_the_tight_tape_gives_every_voter_a_live_reading() -> None:
    """Without this the four-base agreement above could be four abstentions."""
    for base in SCALES:
        rows = _scaled(SHAPES["tight"], base)
        for name in VOTERS:
            sig = _signal(name, rows)
            assert sig.abstained is False, (name, base)
        assert _signal("adx", rows).details["adx"] > 20.0, base
        assert abs(_signal("zscore", rows).details["z"]) > 1.5, base


def test_the_ramp_tape_places_price_high_in_its_own_channel() -> None:
    """The paired control for ``bb_position`` and ``body_pct``."""
    for base in SCALES:
        rows = _scaled(SHAPES["ramp"], base)
        result = detect_bb_proximity(candles_from_raw(rows))
        assert result.bb_position > 0.85, (base, result)
        bodies = [c.body_pct for c in compute_heikin_ashi(candles_from_raw(rows))]
        assert max(bodies) > 50.0, (base, max(bodies))


def test_the_thin_tape_credits_a_money_flow_and_a_volume_ratio() -> None:
    """The paired control for ``mfi`` and ``vol_ratio``."""
    for base in SCALES:
        details = _signal("volume", _scaled(SHAPES["thin"], base)).details
        assert details["mfi"] not in (50.0, 100.0), (base, details["mfi"])
        assert details["vol_ratio"] > 0.0, (base, details)


def test_the_halt_tape_leaves_stochastic_rsi_with_no_window() -> None:
    """The paired control for ``StochasticRSI.window_is_flat``."""
    for base in SCALES:
        sig = _signal("stochastic_rsi", _scaled(SHAPES["halt"], base))
        assert sig.abstained is True, base
        assert sig.confidence == 0.0, (base, sig.confidence)


@pytest.mark.parametrize("base", SCALES)
def test_a_window_with_no_range_abstains_at_every_price_scale(base: float) -> None:
    """``_window_has_no_range`` carries the zero, not an epsilon."""
    rows = _flat(base)
    for name in ("adx", "stochastic_rsi", "zscore"):
        sig = _signal(name, rows)
        assert sig.abstained is True, (name, base)
        assert sig.confidence == 0.0, (name, base, sig.confidence)


# ── the negative controls ────────────────────────────────────────────
def test_an_absolute_epsilon_moves_the_cloud_thickness_with_price_scale() -> None:
    """Drive Ichimoku's own cloud through ``price + 1e-9`` and watch it slide."""
    shipped, epsilon = {}, {}
    for base in SCALES:
        candles = candles_from_raw(_scaled(SHAPES["trend_down"], base))
        _t, _k, senkou_a, senkou_b, _c = IchimokuCloud().lines(candles)[-1]
        thick = abs(senkou_a - senkou_b)
        price = candles[-1].close
        assert thick > 0.0, base
        shipped[base] = thick / price
        epsilon[base] = thick / (price + 1e-9)
    assert _spread(shipped.values()) < CONF_SPREAD, shipped
    assert _spread(epsilon.values()) > EPSILON_SPREAD, epsilon


def test_an_absolute_epsilon_moves_the_z_score_with_price_scale() -> None:
    """The same term against ``ZScoreIndicator``'s own sigma."""
    shipped, epsilon = {}, {}
    period = ZScoreIndicator().period
    for base in SCALES:
        rows = _scaled(SHAPES["tight"], base)
        closes = [r[4] for r in rows][-period:]
        sma = sum(closes) / period
        std = (sum((c - sma) ** 2 for c in closes) / period) ** 0.5
        assert std > 0.0, base
        shipped[base] = (closes[-1] - sma) / std
        epsilon[base] = (closes[-1] - sma) / (std + 1e-9)
    assert _spread(shipped.values()) < 1e-9, shipped
    assert _spread(epsilon.values()) > EPSILON_SPREAD, epsilon


def test_an_absolute_threshold_makes_adx_abstain_only_at_the_low_base() -> None:
    """``s_tr[-1] < 1e-9`` refused a live reading the other bases returned."""
    smoothed = {}
    for base in SCALES:
        candles = candles_from_raw(_scaled(SHAPES["tight"], base))
        indicator = ADXIndicator()
        true_range = [candles[0].high - candles[0].low]
        for i in range(1, len(candles)):
            c, p = candles[i], candles[i - 1]
            true_range.append(
                max(c.high - c.low, abs(c.high - p.close), abs(c.low - p.close))
            )
        smoothed[base] = indicator._wilder_smooth(true_range[1:], indicator.period)[-1]
        assert ADXIndicator().compute(candles).abstained is False, base
    assert min(smoothed.values()) < 1e-9, smoothed
    assert max(smoothed.values()) > 1e-9, smoothed
