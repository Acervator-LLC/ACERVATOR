"""Every indicator's confidence is bounded, and the repaired thresholds
still hold the exact values they held before the repair.

WHY THIS FILE EXISTS. `tests/test_slingshot_confidence_bounds.py` pins
[0, 1] for ONE indicator, because Slingshot is the one that shipped a
`min(1.0, x)` with no floor and reported -0.2722. Eleven other
Signal-returning indicators carried the same one-sided shape and nothing
pinned any of them. The bound matters for the reason that file records:
`Signal.weighted_score` is `direction.value * confidence * weight` and
`VotingEngine._aggregate` adds `abs(ws)` to the winning side, so a
negative confidence does not vote weakly -- the sign is discarded and it
votes with its full magnitude on the side it was meant to doubt.

The second half pins the NUMBERS. Four thresholds were restated as a
percentage divided by `PERCENT_PER_RATIO_UNIT` so their dimensionlessness
is visible in code rather than asserted in a comment. That restatement is
only legitimate while the quotient is bit-identical to the literal it
replaced. These tests fail the moment it is not.

Every positive assertion here has a PAIRED CONTROL that fails when the
mechanism goes blind. A test with no control is not evidence.
"""
from __future__ import annotations

import hashlib
import math
import struct

import pytest

from src.trading.ta_engine import (
    ADXIndicator,
    BollingerBands,
    IchimokuCloud,
    KaufmanERIndicator,
    MACD,
    NO_SHRINK_RATIO,
    PERCENT_PER_RATIO_UNIT,
    RSIIndicator,
    Signal,
    SignalDirection,
    SlingshotIndicator,
    StochasticRSI,
    SupertrendIndicator,
    VX_CEILING,
    VX_FLOOR,
    VolumeAnalysis,
    VortexIndicator,
    VotingEngine,
    VotingSummary,
    ZScoreIndicator,
    candles_from_raw,
    detect_bb_proximity,
    detect_volume_confirmed_spring,
)

INDICATORS = [
    ADXIndicator, SupertrendIndicator, ZScoreIndicator, KaufmanERIndicator,
    BollingerBands, VortexIndicator, MACD, StochasticRSI, IchimokuCloud,
    VolumeAnalysis, RSIIndicator, SlingshotIndicator,
]

# Market shapes a synthetic ramp hides: a flat tape with zero range, a
# sub-cent price, a crash, a chop, and a squeeze that pops.
REGIMES = ["baseline", "chop", "lowvol", "deadflat", "subcent", "crash",
           "melt_up", "squeeze_then_pop"]


def _stream(seed: str):
    """Deterministic normal draws from SHA-256.

    `random.gauss` is a CPython implementation detail and is not pinned
    across versions; a test that must outlive an interpreter upgrade
    cannot rest on it.
    """
    state = {"n": 0}

    def draw(mu: float, sigma: float) -> float:
        vals = []
        for _ in range(2):
            digest = hashlib.sha256(
                seed.encode() + struct.pack("<Q", state["n"])).digest()
            state["n"] += 1
            vals.append(struct.unpack("<Q", digest[:8])[0] / 2.0 ** 64)
        u1 = max(vals[0], 1e-300)
        return mu + sigma * math.sqrt(-2.0 * math.log(u1)) * math.cos(
            2.0 * math.pi * vals[1])

    return draw


def _series(kind: str, n: int = 260) -> list[list[float]]:
    draw = _stream("bounds-" + kind)
    price = 0.0000045 if kind == "subcent" else 100.0
    rows: list[list[float]] = []
    for i in range(n):
        drift, vol = 0.0002, 0.012
        if kind == "chop":
            drift, vol = 0.0, 0.02
        elif kind == "lowvol":
            drift, vol = 0.0, 0.0008
        elif kind == "deadflat":
            drift, vol = 0.0, 0.0
        elif kind == "crash":
            drift, vol = (-0.05, 0.04) if 200 <= i < 220 else (0.0005, 0.01)
        elif kind == "melt_up":
            drift, vol = (0.06, 0.04) if 200 <= i < 220 else (0.0005, 0.01)
        elif kind == "squeeze_then_pop":
            drift = 0.0 if i < 210 else 0.01
            vol = 0.0006 if i < 210 else 0.03
        price = max(price * (1.0 + draw(drift, vol)), 1e-12)
        op = price * (1.0 + draw(0.0, max(vol, 1e-9) / 6.0))
        high = max(op, price) * (1.0 + abs(draw(0.0, max(vol, 1e-9) / 4.0)))
        low = min(op, price) * (1.0 - abs(draw(0.0, max(vol, 1e-9) / 4.0)))
        vol_print = 0.0 if i == 200 else abs(draw(1000.0, 300.0)) + 50.0
        rows.append([float(1_700_000_000_000 + i * 3_600_000),
                     op, high, low, price, vol_print])
    if kind == "deadflat":
        flat = rows[0][4]
        for row in rows:
            row[1] = row[2] = row[3] = row[4] = flat
    return rows


def _out_of_bounds(values: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """The checker under test. Returns every reading outside [0, 1]."""
    return [(name, value) for name, value in values
            if not 0.0 <= value <= 1.0]


@pytest.mark.parametrize("kind", REGIMES)
def test_every_indicator_confidence_stays_in_zero_one(kind: str) -> None:
    """No indicator may report a confidence outside [0, 1] on any tape."""
    rows = _series(kind)
    readings: list[tuple[str, float]] = []
    for end in range(60, len(rows) + 1, 20):
        candles = candles_from_raw(rows[:end])
        for cls in INDICATORS:
            signal = cls().compute(candles, "1h")
            readings.append(("%s@%d" % (cls.__name__, end), signal.confidence))
    assert readings, "no readings taken: the sweep never ran"
    assert _out_of_bounds(readings) == []


def test_the_bounds_checker_reports_a_one_sided_clamp() -> None:
    """PAIRED CONTROL for the test above.

    A checker that cannot report a violation proves nothing by reporting
    none. These are the two real shapes: `min(1.0, x)` with no floor,
    which is what produced -0.2722, and `max(0.0, x)` with no ceiling,
    which is the shape lines 993/1089/1096 carried.
    """
    floor_open = min(1.0, -0.2722)
    ceiling_open = max(0.0, 1.5)
    caught = _out_of_bounds([("floor_open", floor_open),
                             ("ceiling_open", ceiling_open)])
    assert len(caught) == 2, "the bounds checker is blind"


def test_weighted_score_discards_the_sign_so_the_bound_is_load_bearing() -> None:
    """Why [0, 1] matters: a negative confidence votes at full magnitude."""
    negative = Signal("probe", "1h", SignalDirection.BULLISH, -0.2722, 1.0)
    positive = Signal("probe", "1h", SignalDirection.BULLISH, 0.2722, 1.0)
    assert abs(negative.weighted_score) == abs(positive.weighted_score)


# ---------------------------------------------------------------------------
# The numbers the repair restated. Bit-exact or it is a behaviour change.
# ---------------------------------------------------------------------------

def test_percent_to_ratio_division_is_bit_exact() -> None:
    """`x / PERCENT_PER_RATIO_UNIT` must equal the literal it replaced.

    The whole restatement rests on this. IEEE division is correctly
    rounded, so 130.0 / 100.0 lands on the same double as 1.30 -- but
    that is a fact to CHECK, not to assume, and it is not true for every
    numerator.
    """
    assert float.hex(PERCENT_PER_RATIO_UNIT) == float.hex(100.0)
    for numerator, literal in ((130.0, 1.30), (70.0, 0.70), (200.0, 2.0)):
        assert float.hex(numerator / PERCENT_PER_RATIO_UNIT) == \
            float.hex(literal)


def test_the_bit_exact_check_would_notice_a_moved_value() -> None:
    """PAIRED CONTROL: float.hex separates values `==` would not."""
    assert float.hex(0.1 + 0.2) != float.hex(0.3)


def test_vortex_extremes_hold_their_shipped_values() -> None:
    """VX_CEILING and VX_FLOOR are now quotients. Same doubles as before."""
    assert float.hex(VX_CEILING) == float.hex(1.30)
    assert float.hex(VX_FLOOR) == float.hex(0.70)


def test_volume_spike_threshold_is_still_two_times_average() -> None:
    """The constructor now takes a percent; the stored ratio is unmoved."""
    assert float.hex(VolumeAnalysis().spike_threshold) == float.hex(2.0)
    assert float.hex(
        VolumeAnalysis(spike_threshold_pct=350.0).spike_threshold) == \
        float.hex(3.5)


def test_unit_references_are_exactly_one() -> None:
    """`x / 1.0` is exact for every float; that is why these are 1.0."""
    assert float.hex(NO_SHRINK_RATIO) == float.hex(1.0)
    for probe in (0.0, -0.0, 3.0, 1e-300, 1e300, 0.1, 2.2250738585072014e-308):
        assert float.hex(probe / NO_SHRINK_RATIO) == float.hex(probe)


def test_vortex_signal_is_scale_invariant() -> None:
    """VI+ and VI- are ratios, so the signal cannot depend on price level.

    This is the Bollinger incident's test, applied to the thresholds this
    unit restated. If VX_CEILING ever stops being dimensionless, a
    thousand-fold price scaling changes the answer -- which is exactly
    how the squeeze flag reduced to `mid > 1.33`.
    """
    rows = _series("baseline")
    scaled = [[r[0], r[1] * 1000.0, r[2] * 1000.0, r[3] * 1000.0,
               r[4] * 1000.0, r[5]] for r in rows]
    plain = VortexIndicator().compute(candles_from_raw(rows), "1h")
    big = VortexIndicator().compute(candles_from_raw(scaled), "1h")
    assert plain.direction == big.direction
    assert plain.details["vi_plus"] == pytest.approx(
        big.details["vi_plus"], rel=1e-9)
    assert plain.details["vip_at_ceiling"] == big.details["vip_at_ceiling"]
    assert plain.details["vim_at_ceiling"] == big.details["vim_at_ceiling"]


def test_scale_invariance_check_would_notice_a_price_dependent_flag() -> None:
    """PAIRED CONTROL: the comparison above can distinguish the scales."""
    rows = _series("baseline")
    scaled = [[r[0], r[1] * 1000.0, r[2] * 1000.0, r[3] * 1000.0,
               r[4] * 1000.0, r[5]] for r in rows]
    plain = BollingerBands().compute(candles_from_raw(rows), "1h")
    big = BollingerBands().compute(candles_from_raw(scaled), "1h")
    # `middle` is a PRICE and must scale; if it does not, the two tapes
    # are the same tape and the invariance test above is vacuous.
    assert plain.details["middle"] != big.details["middle"]


def test_spring_survives_a_summary_with_no_bollinger_position() -> None:
    """The absent-position branch is reachable and must stay a sentinel.

    `BollingerBands.compute` returns a Signal with NO details when it has
    fewer candles than its period, so `details.get("bb_position")` is
    None on the real path. The composite must report the -1.0 sentinel
    and refuse to trigger, not raise.
    """
    short = candles_from_raw(_series("baseline")[:5])
    summary = VotingEngine().compute_all(short, "1h")
    assert isinstance(summary, VotingSummary)
    bollinger = [s for s in summary.signals
                 if s.indicator == "bollinger_bands"]
    assert bollinger, "no bollinger signal in the summary"
    assert bollinger[0].details.get("bb_position") is None
    result = detect_volume_confirmed_spring(
        summary, detect_bb_proximity(short))
    assert result["bb_position"] == -1.0
    assert result["triggered"] is False
    assert result["components_met"] == 0


def test_spring_reads_a_present_bollinger_position() -> None:
    """PAIRED CONTROL: the sentinel above is not the only answer it gives."""
    full = candles_from_raw(_series("baseline"))
    summary = VotingEngine().compute_all(full, "1h")
    result = detect_volume_confirmed_spring(summary, detect_bb_proximity(full))
    assert result["bb_position"] != -1.0
