"""An undefined quantity produces NO VOTE, never an extreme of the scale.

THE RULE THIS FILE PINS. When a denominator is exactly zero on an
admissible bar, the quantity is UNDEFINED and the unit must abstain --
each indicator returning its own warm-up neutral, each non-voting helper
returning no detection -- and no epsilon, floor or clamp may stand in for
that decision.

WHY IT EXISTS. Nineteen division sites in `ta_engine.py` resolved 0/0 to
a definite number, and at six of them that number was an extreme of the
output scale, i.e. maximum conviction. Measured on a halted market before
the repair: BollingerBands voted BULLISH at confidence 1.000 on weight
1.0, RSI voted BULLISH at 1.000 on weight 0.8, and the engine's consensus
came out BULLISH at net +2.011 -- the BUY side open and the FOLD side
shut on a market that had not moved. Vortex reached VI+ = 2.2e8 and
inverted its own direction; Slingshot saturated to BEARISH 1.0000.

WHAT A FAILURE HERE MEANS, per test class:
  * An ABSTENTION test failing means a site's guard is no longer on the
    path its vote takes -- the undefined quantity is reaching the scale
    again, and a halted or pegged book can move real money.
  * A LIVE-BAND test failing means the repair over-reached: it silenced
    an indicator on a bar whose denominator was genuinely non-zero, and
    the engine has lost a vote it was entitled to cast.
  * The BIT-IDENTITY test failing means the change touched well-formed
    data, which the repair was scoped never to do.

Every abstention assertion is PAIRED with a live-band control that fails
when the mechanism goes blind, because a test that can only ever pass is
not evidence. The pairing is deliberate: `test_bollinger_abstains_on_zero
_width_band` and `test_bollinger_still_votes_bullish_at_pct_b_002` fail
in OPPOSITE directions, so no single wrong constant satisfies both.
"""

from __future__ import annotations

import hashlib
import math
import struct

import pytest

from src.trading.ta_engine import (
    ADXIndicator,
    _stdev_tail,
    BollingerBands,
    KaufmanERIndicator,
    RSIIndicator,
    SlingshotIndicator,
    StochasticRSI,
    VolumeAnalysis,
    VortexIndicator,
    VotingEngine,
    ZScoreIndicator,
    candles_from_raw,
    compute_heikin_ashi,
    detect_bb_proximity,
    detect_landing_strip_v2,
)
from src.trading.ta_engine import SignalDirection as SD

LCG_A = 1664525
LCG_C = 1013904223
LCG_M = 4294967296


def _lcg(seed: int):
    """A reproducible uniform source built from literal constants.

    Not `random`: the series must be identical on every machine, because
    the bit-identity test hashes what it produces.
    """
    state = seed % LCG_M

    def nxt() -> float:
        nonlocal state
        state = (LCG_A * state + LCG_C) % LCG_M
        return state / LCG_M

    return nxt


# A flat 20-bar window leaves `_stdev_tail` at exactly 0.0 for a cancelling
# peg and strictly positive for a non-cancelling one.
CANCELLING_PEGS = (100.0, 3.2e-05, 1.0, 1.43)
NON_CANCELLING_PEGS = (118.39, 0.11, 61234.03, 0.03120002)
ALL_PEGS = CANCELLING_PEGS + NON_CANCELLING_PEGS


def flat_rows(n: int, price: float, volume: float = 0.0) -> list[list[float]]:
    """A halt or a pegged book: open == high == low == close, every bar.

    The screen admits this -- price > 0, finite, low <= high, and open
    and close both inside [low, high] with equality throughout -- so
    nothing pinned here is latent.
    """
    return [[float(i), price, price, price, price, volume] for i in range(n)]


def realistic_rows(n: int = 400, base: float = 100.0) -> list[list[float]]:
    """Well-formed data: drift plus bounded noise, no zero denominators."""
    rng = _lcg(11)
    rows: list[list[float]] = []
    prev_close = base
    for i in range(n):
        drift = math.sin(i / 40.0) * (base * 0.06)
        close = base + drift + (rng() - 0.5) * (base * 0.012)
        open_px = prev_close
        top = max(open_px, close) + abs(rng() - 0.5) * (base * 0.006)
        bottom = min(open_px, close) - abs(rng() - 0.5) * (base * 0.006)
        rows.append([float(i), open_px, top, bottom, close, 800.0 + rng() * 400.0])
        prev_close = close
    return rows


def monotone_rows(n: int = 400) -> list[list[float]]:
    """Every bar up. No down bar, so the RSI window has zero range while
    the price tape does not -- this separates the two conditions."""
    rows: list[list[float]] = []
    for i in range(n):
        open_px = 100.0 + i * 0.25
        close = open_px + 0.25
        rows.append([float(i), open_px, close, open_px, close, 500.0])
    return rows


def halt_after_real(real_n: int, halt_n: int, base: float = 100.0) -> list[list[float]]:
    """Real history, then the venue stops."""
    rows = realistic_rows(real_n, base)
    last = rows[-1][4]
    for i in range(halt_n):
        rows.append([float(real_n + i), last, last, last, last, 0.0])
    return rows


@pytest.fixture(scope="module")
def flat() -> list:
    """118.39, NOT 100.0. See the peg table: at 100.0 sigma cancels to
    exactly 0.0 and a width-based guard passes this fixture for the
    wrong reason. 118.39 leaves sigma at 1.42e-14, so only a guard on
    the SOURCE window can satisfy it."""
    return candles_from_raw(flat_rows(400, 118.39))


@pytest.fixture(scope="module")
def flat_subcent() -> list:
    """0.03120002 -- the operator's SPK scale -- NOT 3.2e-05. Sub-cent
    AND non-cancelling, so this stays a scale control while also
    refusing the arithmetically convenient case."""
    return candles_from_raw(flat_rows(400, 0.03120002))


@pytest.fixture(scope="module")
def healthy() -> list:
    return candles_from_raw(realistic_rows())


def test_the_degenerate_series_are_admitted_by_the_real_screen() -> None:
    """If this fails, every other test in the file is latent -- it would
    be driving bars the production path already rejects, and the findings
    would say nothing about live trading."""
    tapes = [flat_rows(400, p) for p in ALL_PEGS]
    tapes += [
        flat_rows(400, 118.39, 900.0),
        halt_after_real(300, 30),
        monotone_rows(),
        flat_rows(1, 118.39),
    ]
    for rows in tapes:
        assert len(candles_from_raw(rows)) == len(rows)


def test_the_peg_table_still_spans_both_classes() -> None:
    """THE GUARD ON THE FIXTURE ITSELF.

    If this fails, the peg table has drifted back to prices where the
    rounding cancels, and every abstention test in this file would then
    be satisfiable by a guard on the DERIVED band width -- the exact
    defect that let a halted market vote BULLISH at confidence 1.0000
    while a repair and its tests both reported success.

    It asserts the property directly rather than restating the constants:
    each CANCELLING peg must leave sigma at exactly 0.0, and each
    NON_CANCELLING peg must leave it strictly positive.
    """
    for peg in CANCELLING_PEGS:
        sigma = _stdev_tail([peg] * 20, 20, tail=1)[-1]
        assert sigma == 0.0, (peg, sigma)
    for peg in NON_CANCELLING_PEGS:
        sigma = _stdev_tail([peg] * 20, 20, tail=1)[-1]
        assert sigma > 0.0, (peg, sigma)
        # And the halted window really is halted at the source.
        assert max([peg] * 20) == min([peg] * 20)
        # The Bollinger band width is 2 * std_dev * sigma, so at these pegs
        # a width guard cannot fire on a halted market.
        assert 2.0 * 2.0 * sigma > 0.0, (peg, sigma)


@pytest.mark.parametrize("peg", ALL_PEGS)
def test_bollinger_abstains_at_every_peg(peg: float) -> None:
    """THE NEW-1 REGRESSION, driven over both halves of the table.

    A failure on a CANCELLING peg means the guard is gone entirely. A
    failure on a NON_CANCELLING peg means the guard is back on the
    derived band width, which does not reach zero on a halt.
    """
    sig = BollingerBands().compute(candles_from_raw(flat_rows(400, peg)), "1h")
    assert sig.direction is SD.NEUTRAL, (peg, sig.direction, sig.confidence)
    assert sig.confidence == 0.0, (peg, sig.confidence)


@pytest.mark.parametrize("peg", ALL_PEGS)
def test_no_landing_strip_at_any_peg(peg: float) -> None:
    """The fabricated `mid * 0.01` band made a bandless market produce a
    landing strip on the "upper" side while the same object reported
    bb_position 0.0. That flag is read in `ScrummingBot.tick`
    (`src/trading/scrumming_bot.py`), which sets `is_bullish = True`
    WITHOUT consulting the confidence floor, so a failure here reaches
    a trade decision directly."""
    candles = candles_from_raw(flat_rows(400, peg))
    prox = detect_bb_proximity(candles)
    assert not prox.landing_strip, (peg, prox)
    assert not prox.near_upper and not prox.near_lower, (peg, prox)
    assert prox.landing_strip_side == "", (peg, prox)
    assert prox.bb_position == 0.5, (peg, prox)
    assert not detect_landing_strip_v2(candles).detected, peg


# ── F01 -------------------------------------------------------------------
def test_bollinger_abstains_on_zero_width_band(flat: list) -> None:
    sig = BollingerBands().compute(flat, "1h")
    assert sig.direction is SD.NEUTRAL
    assert sig.confidence == 0.0


def test_bollinger_abstains_at_subcent_price_too(flat_subcent: list) -> None:
    """Scale control: the defect was never a small-number artefact, so the
    repair must not be one either."""
    sig = BollingerBands().compute(flat_subcent, "1h")
    assert sig.direction is SD.NEUTRAL
    assert sig.confidence == 0.0


def _quiet_base() -> list[list[float]]:
    rng = _lcg(5)
    rows: list[list[float]] = []
    for i in range(60):
        close = 100.0 + (rng() - 0.5) * 4.0
        rows.append([float(i), close, close + 0.5, close - 0.5, close, 700.0])
    return rows


def _pct_b_for(close: float) -> tuple[float, object]:
    rows = _quiet_base()
    rows.append([60.0, close, close + 0.01, close - 0.01, close, 700.0])
    sig = BollingerBands().compute(candles_from_raw(rows), "1h")
    return sig.details["bb_position"], sig


def test_bollinger_still_votes_bullish_at_pct_b_002() -> None:
    """THE PAIRED CONTROL for F01, and the one the audit named. A genuine
    %B of 0.02 on a LIVE band is an ordinary strong-oversold reading. If
    the zero-width guard swallowed it, the repair has reached past the
    degenerate case into real trading.

    The closing price is SOLVED for rather than assumed: appending a bar
    shifts the 20-bar mean and sigma, so a price computed from the
    pre-append band does not land where it was aimed. Bisection is
    deterministic and needs no magic constant.
    """
    lo, hi = 90.0, 100.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if _pct_b_for(mid)[0] > 0.02:
            hi = mid
        else:
            lo = mid
    pct_b, sig = _pct_b_for((lo + hi) / 2)

    assert pct_b == pytest.approx(
        0.02, abs=0.001
    ), f"fixture did not land on %B = 0.02: {pct_b}"
    assert sig.details["band_width"] > 0.0, "control needs a LIVE band"
    assert sig.direction is SD.BULLISH
    assert sig.confidence > 0.9


# ── F02 -------------------------------------------------------------------
@pytest.mark.parametrize("peg", ALL_PEGS)
def test_bb_proximity_names_no_side_when_both_bands_are_near(peg: float) -> None:
    """The channel is narrower than the tolerance, so neither side is the
    one price is reverting FROM. Before the repair this reported
    landing_strip_side == "upper" -- a SELL -- while its own bb_position
    field said price sat hard against the LOWER band."""
    res = detect_bb_proximity(candles_from_raw(flat_rows(400, peg)))
    assert res.landing_strip is False, (peg, res)
    assert res.landing_strip_side == "", (peg, res)


@pytest.mark.parametrize("peg", ALL_PEGS)
def test_landing_strip_v2_names_no_side_when_both_bands_are_near(peg: float) -> None:
    """THE FIXTURE CHANGED, and the reason is the point of this file.

    This drove `flat_rows(400, 100.0)`. MEASURED against the pre-repair
    tree that form PASSES: a plain flat tape gives a zero normalised
    body, the shrink loop breaks on its first step and the function
    returns at its Layer-1 length check, so the side-assignment branch
    this test names is never reached. A test that cannot fail is not
    evidence, whatever it asserts.

    `const_close_shrinking_bodies` DOES reach Layer 2, and the assertion
    is unchanged: a window with no channel names no side. Measured, the
    new form fails on the pre-repair tree at every peg, and on the
    BLOCKED derived-width repair at all four NON_CANCELLING pegs -- it
    reported side "lower" with bb_position 0.0134 at 118.39.
    """
    res = detect_landing_strip_v2(
        candles_from_raw(const_close_shrinking_bodies(price=peg))
    )
    assert (
        res.raw_tightenings >= 3
    ), "fixture must reach Layer 2, or the branch is never entered"
    assert res.detected is False, (peg, res)
    assert res.side == "", (peg, res)


def _rally_into_upper_band(steps: int = 5) -> list[list[float]]:
    """A quiet range, then a decelerating rally that ends against the
    upper band. Bodies shrink each step, which is what the v2 detector
    keys on, and the close sits above the 20-bar mean, which is what puts
    it near the band."""
    rng = _lcg(3)
    rows: list[list[float]] = []
    prev = 100.0
    for i in range(26):
        close = 100.0 + (rng() - 0.5) * 1.2
        rows.append(
            [
                float(i),
                prev,
                max(prev, close) + 0.15,
                min(prev, close) - 0.15,
                close,
                700.0,
            ]
        )
        prev = close
    step = 3.0
    for j in range(steps):
        close = prev + step
        rows.append([float(26 + j), prev, close + 0.05, prev - 0.05, close, 700.0])
        prev = close
        step *= 0.5
    return rows


def _selloff_into_lower_band() -> list[list[float]]:
    """The mirror of the rally, reflected about 200. Same shape, opposite
    side."""
    return [
        [r[0], 200.0 - r[1], 200.0 - r[3], 200.0 - r[2], 200.0 - r[4], r[5]]
        for r in _rally_into_upper_band()
    ]


def test_bb_proximity_still_names_upper_on_a_live_one_sided_band() -> None:
    """THE PAIRED CONTROL for F02. A real approach to the UPPER band on a
    live channel must still be detected and still be called "upper".

    `consolidation_threshold` is opened up because this control exists to
    exercise the SIDE-ASSIGNMENT branch, not the tightness threshold; the
    band proximity it turns on is genuine and one-sided.
    """
    res = detect_bb_proximity(
        candles_from_raw(_rally_into_upper_band()),
        tolerance_pct=5.0,
        consolidation_threshold=100.0,
    )
    assert res.near_upper is True
    assert res.near_lower is False
    assert res.landing_strip is True
    assert res.landing_strip_side == "upper"


def test_bb_proximity_names_lower_when_only_the_lower_band_is_near() -> None:
    """THE MIRROR, and it is the sharpest form of this control. The
    pre-repair `if/elif` resolved every tie to "upper"; a test that only
    ever asserted "upper" would have passed against the defect. This one
    demands the OTHER answer on the mirrored tape.

    This is the audit's "7 of 138 detections report upper while price sits
    in the lower half" reproduced deterministically: here bb_position is
    below 0.05 and the reported side must agree with it.
    """
    res = detect_bb_proximity(
        candles_from_raw(_selloff_into_lower_band()),
        tolerance_pct=5.0,
        consolidation_threshold=100.0,
    )
    assert res.bb_position < 0.5, "fixture must sit in the LOWER half"
    assert res.near_lower is True
    assert res.near_upper is False
    assert res.landing_strip is True
    assert res.landing_strip_side == "lower"


def test_landing_strip_v2_still_names_upper_on_a_live_one_sided_band() -> None:
    """The same control for the second F02 site, the ternary at :3429."""
    res = detect_landing_strip_v2(
        candles_from_raw(_rally_into_upper_band()), bb_tolerance_pct=3.0
    )
    assert res.detected is True
    assert res.side == "upper"
    assert res.bb_position > 0.5


# ── Vortex ----------------------------------------------------------------
@pytest.mark.parametrize("halt", list(range(14, 24)))
def test_vortex_abstains_once_the_halt_fills_the_true_range_window(halt: int) -> None:
    """The overshoot lives at ONE halt length -- 14, the period -- because
    true range is aligned to bar i while the VM sums reach back to i-1. A
    test at a single fixed length steps straight over it."""
    candles = candles_from_raw(halt_after_real(300, halt))
    sig = VortexIndicator().compute(candles, "1h")
    assert sig.direction is SD.NEUTRAL
    assert sig.confidence == 0.0
    vi_plus = (sig.details or {}).get("vi_plus", 0.0)
    assert abs(vi_plus) < 10.0, f"VI+ reached {vi_plus}"


def test_vortex_still_votes_before_the_halt_fills_the_window() -> None:
    """THE PAIRED CONTROL. At halt 13 the true-range sum is still positive
    and Vortex is entitled to its reading."""
    candles = candles_from_raw(halt_after_real(300, 13))
    sig = VortexIndicator().compute(candles, "1h")
    assert sig.direction is not SD.NEUTRAL
    assert sig.confidence > 0.0


# ── RSI + StochasticRSI ---------------------------------------------------
@pytest.mark.parametrize("peg", ALL_PEGS)
def test_rsi_abstains_on_a_flat_window(peg: float) -> None:
    """Both averages are exactly zero, so RS is 0/0. Through the epsilon
    that produced rsi == 0.0 exactly -- the bottom of the scale -- read as
    maximum oversold and voted BULLISH at confidence 1.0000."""
    sig = RSIIndicator().compute(candles_from_raw(flat_rows(400, peg)), "1h")
    assert sig.direction is SD.NEUTRAL, (peg, sig.direction)
    assert sig.confidence == 0.0, (peg, sig.confidence)


def test_rsi_still_reports_overbought_when_there_are_no_losses() -> None:
    """THE PAIRED CONTROL, and it guards the CANON. Wilder defines RS with
    no losses but SOME gains as an infinite ratio, i.e. RSI 100. That case
    is defined and must keep voting; only 0/0 abstains."""
    sig = RSIIndicator().compute(candles_from_raw(monotone_rows()), "1h")
    assert sig.direction is SD.BEARISH
    assert sig.confidence > 0.9


@pytest.mark.parametrize("peg", ALL_PEGS)
def test_stochastic_rsi_abstains_on_a_flat_window(peg: float) -> None:
    sig = StochasticRSI().compute(candles_from_raw(flat_rows(400, peg)), "1h")
    assert sig.direction is SD.NEUTRAL, (peg, sig.direction)
    assert sig.confidence == 0.0, (peg, sig.confidence)


def test_stochastic_rsi_abstains_when_the_rsi_window_has_no_range() -> None:
    """A monotone tape pins RSI at its ceiling, so the stochastic asks
    where 100 sits within [100, 100]. Through the epsilon that resolved to
    0.0 -- the BOTTOM of the stochastic range -- and voted BULLISH on a
    relentlessly rising market."""
    sig = StochasticRSI().compute(candles_from_raw(monotone_rows()), "1h")
    assert sig.direction is SD.NEUTRAL
    assert sig.confidence == 0.0


# ── the remaining Group A units -------------------------------------------
@pytest.mark.parametrize("peg", ALL_PEGS)
def test_volume_abstains_when_the_window_traded_nothing(peg: float) -> None:
    sig = VolumeAnalysis().compute(candles_from_raw(flat_rows(400, peg)), "1h")
    assert sig.direction is SD.NEUTRAL, (peg, sig.direction)
    assert sig.confidence == 0.0, (peg, sig.confidence)


def test_volume_still_votes_when_price_is_flat_but_volume_is_not() -> None:
    """THE PAIRED CONTROL, and it separates two conditions that a
    price-only fixture would confound: the volume site keys on ZERO
    VOLUME, not on a zero price range."""
    candles = candles_from_raw(flat_rows(400, 100.0, volume=900.0))
    sig = VolumeAnalysis().compute(candles, "1h")
    assert sig.details, "volume abstained on a window that did trade"


@pytest.mark.parametrize("peg", ALL_PEGS)
def test_kaufman_er_abstains_when_price_never_moved(peg: float) -> None:
    """NOT A REGRESSION PIN, and saying so is the honest reading.

    MEASURED on the pre-repair tree at all eight pegs, this already
    returned NEUTRAL 0.0: KaufmanER's `price_travel` is a sum of
    |close[i] - close[i-1]| over IDENTICAL floats, so every term is
    exactly 0.0 and the quantity cancels at every scale. The repair
    replaced an epsilon with a source test at that site and changed no
    output. This arm therefore cannot be shown failing against the
    pre-repair code -- it documents a property, it does not pin a
    change, and it is kept only so the site stays covered when the
    guard is next touched.
    """
    sig = KaufmanERIndicator().compute(candles_from_raw(flat_rows(400, peg)), "1h")
    assert sig.direction is SD.NEUTRAL, (peg, sig.direction)
    assert sig.confidence == 0.0, (peg, sig.confidence)


@pytest.mark.parametrize("peg", ALL_PEGS)
def test_slingshot_abstains_when_there_is_no_volatility_unit(peg: float) -> None:
    """Driven at every peg, because Slingshot's bandwidths are
    `2 * bb_std * sigma / mid` and inherit the same rounding the band
    width does. Measured, this fails on the pre-repair tree at every peg
    and at all three halt lengths."""
    for halt in (20, 22, 25):
        candles = candles_from_raw(halt_after_real(300, halt, peg))
        sig = SlingshotIndicator().compute(candles, "1h")
        assert sig.direction is SD.NEUTRAL, (peg, halt, sig.direction)
        assert sig.confidence == 0.0, (peg, halt, sig.confidence)


def const_close_shrinking_bodies(
    n: int = 30, price: float = 100.0
) -> list[list[float]]:
    """Every CLOSE identical, but the bodies shrink because the OPEN moves.

    This is the only shape that reaches the v2 detector's band floor. A
    plain flat tape cannot: its shrink loop sees a zero normalised body,
    breaks, and returns before the floor is evaluated. Here the closes
    give a zero-width channel while the opens supply the consecutive
    shrinking bodies the detector needs to get past Layer 1.

    THE BODY IS A FRACTION OF THE PRICE, and there is no absolute floor.
    Both were price-scale constants before -- a body of 2.0 and a floor
    of 1e-9 -- so the fixture only reached Layer 2 near $100. MEASURED at
    3.2e-05 the old form returned raw_tightenings = 0 on all three trees:
    the floor pinned every body to 1e-9, consecutive bodies came out
    EQUAL rather than shrinking, the run broke at once and the test drove
    a branch it never entered. The detector reads a NORMALISED body
    (body / close), so scaling the body to the price makes the series it
    sees identical at every peg, which is the only way one assertion can
    span 3.2e-05 and 61234.03.
    """
    rows: list[list[float]] = []
    body = price * 0.02
    for i in range(n):
        open_px = price - body
        rows.append(
            [float(i), open_px, max(open_px, price), min(open_px, price), price, 700.0]
        )
        body *= 0.7
    return rows


@pytest.mark.parametrize("peg", ALL_PEGS)
def test_bb_proximity_reports_no_position_when_there_is_no_channel(peg: float) -> None:
    """Pins the REMOVAL OF THE FABRICATED BAND, distinctly from the side
    logic. `bb_range = mid * 0.01` invented a 1%-of-price channel that no
    published source defines; with it, a bandless market reported
    bb_position 0.0 -- hard against a lower band that does not exist --
    and BOTH proximity flags true.

    Measured: with the floor restored, bb_position returns to 0.0 and
    near_upper and near_lower both flip to True on this exact tape.
    """
    res = detect_bb_proximity(candles_from_raw(flat_rows(400, peg)))
    assert res.bb_position == 0.5, (peg, res.bb_position)
    assert res.near_upper is False, (peg, res)
    assert res.near_lower is False, (peg, res)


@pytest.mark.parametrize("peg", ALL_PEGS)
def test_landing_strip_v2_reports_no_position_when_there_is_no_channel(
    peg: float,
) -> None:
    """The same fabricated floor in the v2 detector, on the only tape that
    reaches it. Measured: restoring the floor moves bb_position from 0.5
    to 0.0.

    Driven over BOTH halves of the peg table. On the BLOCKED
    derived-width repair this passes at every CANCELLING peg and fails
    at every NON_CANCELLING one, which is exactly the discrimination a
    100.0-only fixture could not make.
    """
    res = detect_landing_strip_v2(
        candles_from_raw(const_close_shrinking_bodies(price=peg))
    )
    assert res.detected is False, (peg, res)
    assert res.bb_position == 0.5, (peg, res.bb_position)
    assert (
        res.raw_tightenings >= 3
    ), "fixture must reach Layer 2, or the floor is never evaluated"


@pytest.mark.parametrize("peg", ALL_PEGS)
def test_kaufman_er_previous_window_falls_back_to_the_current_reading(
    peg: float,
) -> None:
    """A previous window that never moved has no efficiency ratio. The
    module's own fallback is the current reading, and `er_rising` must not
    claim a rise that was never measured.

    Measured: with the epsilon restored, er_prev reads 0.0 instead of 1.0
    and `er_rising` flips False -> True, inventing a trend from 0/0.
    """
    rows = flat_rows(60, peg)
    rows.append([60.0, peg, peg * 1.01, peg, peg * 1.01, 100.0])
    sig = KaufmanERIndicator().compute(candles_from_raw(rows), "1h")
    assert sig.details["er_prev"] == sig.details["er"], (peg, sig.details)
    assert sig.details["er_rising"] is False, (peg, sig.details)


@pytest.mark.parametrize("peg", ALL_PEGS)
def test_zscore_previous_window_falls_back_to_the_current_reading(peg: float) -> None:
    """Measured: with the epsilon restored, z_prev reads 0.0 rather than
    the current z, so the indicator reports a previous position it never
    measured.

    Driven at every peg deliberately. The site's guard is
    `if not std2 < 1e-9`, an EPSILON on a derived quantity rather than a
    source test, and an epsilon can only ever abstain too early. Running
    both halves of the table is what shows it does not abstain too late:
    at 118.39 the previous window's sigma is 1.42e-14, which an exact
    `std2 > 0.0` test would have let straight through.
    """
    rows = flat_rows(60, peg)
    rows.append([60.0, peg, peg * 1.01, peg, peg * 1.01, 100.0])
    sig = ZScoreIndicator().compute(candles_from_raw(rows), "1h")
    assert sig.details["z_prev"] == sig.details["z"], (peg, sig.details)


@pytest.mark.parametrize("peg", ALL_PEGS)
def test_zscore_keeps_its_reading_and_reports_no_reversion(peg: float) -> None:
    """THE PAIRED CONTROL for the arm above, and it is a control rather
    than a pin: it passes on the pre-repair tree too, by design. Its job
    is to fail if the abstention ever widens into the vote itself.

    The z is well defined here; only the PREVIOUS window's sigma is zero.
    The unit must keep the vote it earned and decline only the claim it
    cannot support -- the direction of travel.
    """
    rows = flat_rows(60, peg)
    rows.append([60.0, peg, peg * 1.01, peg, peg * 1.01, 100.0])
    sig = ZScoreIndicator().compute(candles_from_raw(rows), "1h")
    assert sig.direction is SD.BEARISH, (peg, sig.direction)
    assert sig.details["z_reverting"] is False, (peg, sig.details)


@pytest.mark.parametrize("peg", ALL_PEGS)
def test_heikin_ashi_reports_no_body_ratio_when_a_bar_has_no_range(peg: float) -> None:
    """0.0 is not neutral for this field: the only consumer tests
    `body_pct <= threshold`, so zero is the TIGHTEST possible reading and
    manufactured a consolidation from a market that had not moved."""
    ha = compute_heikin_ashi(candles_from_raw(flat_rows(400, peg)))
    assert math.isnan(ha[-1].body_pct), (peg, ha[-1].body_pct)


def test_heikin_ashi_still_measures_a_body_on_a_live_bar(healthy: list) -> None:
    """THE PAIRED CONTROL: every bar of well-formed data keeps a number."""
    ha = compute_heikin_ashi(healthy)
    assert not any(math.isnan(c.body_pct) for c in ha)


@pytest.mark.parametrize("peg", ALL_PEGS)
def test_adx_dx_series_survives_a_zero_true_range_window(peg: float) -> None:
    """NOT A REGRESSION PIN either, and for the same reason as the
    KaufmanER arm above.

    MEASURED on the pre-repair tree at all eight pegs: already NEUTRAL
    0.0. Directional movement can never exceed true range, so a zero
    Wilder true-range sum forces the DM sums to zero too, and the old
    `ds > 1e-9 else 0.0` fallback already appended the same 0.0 the new
    explicit branch does. The repair at that site documents an intent
    and removes a 0/0; it changes no output, and this arm cannot be
    shown failing against the pre-repair code.
    """
    sig = ADXIndicator().compute(candles_from_raw(flat_rows(400, peg)), "1h")
    assert sig.direction is SD.NEUTRAL, (peg, sig.direction)
    assert sig.confidence == 0.0, (peg, sig.confidence)


# ── the engine-level consequence -----------------------------------------
@pytest.mark.parametrize("peg", ALL_PEGS)
def test_a_halted_market_no_longer_opens_the_buy_side(peg: float) -> None:
    """The reason this unit exists. Before the repair the engine's own
    aggregation returned net +2.011 and consensus BULLISH on a market that
    had not moved -- `is_bullish` True, so the BUY side was open.

    On the BLOCKED derived-width repair this passes at every CANCELLING
    peg and fails at every NON_CANCELLING one. It is the sharpest single
    arm in the file: one assertion, at the engine's own output, that
    separates a guard on the source window from a guard on the width.
    """
    summary = VotingEngine().compute_all(candles_from_raw(flat_rows(400, peg)), "1h")
    assert summary.consensus_direction is not SD.BULLISH, (
        peg,
        summary.consensus_direction,
        summary.net_score,
    )
    assert summary.net_score < 0.1, (peg, summary.net_score)


# ── the opposite control --------------------------------------------------
def _hash_signal(sig) -> str:
    digest = hashlib.sha256()
    digest.update(sig.indicator.encode())
    digest.update(sig.direction.name.encode())
    digest.update(struct.pack("<d", float(sig.confidence)))
    digest.update(struct.pack("<d", float(sig.weight)))
    for key in sorted((sig.details or {}).keys()):
        digest.update(key.encode())
        digest.update(repr(sig.details[key]).encode())
    return digest.hexdigest()[:16]


# `_hash_signal` over `realistic_rows`, taken before the abstention repair.
EXPECTED_HEALTHY_HASHES = {
    "adx": "a21a68f11b0ebe4e",
    "bollinger_bands": "d15bd21c3a386958",
    "ichimoku": "5d584593ca7a1c7e",
    "kaufman_er": "49a171528a8e7876",
    "macd": "93bd545133023f59",
    "rsi": "846a05fa23dac836",
    "slingshot": "217d6d34260b66c6",
    "stochastic_rsi": "3e3911f241b15bb2",
    "supertrend": "43d753765bd80aa9",
    "volume": "fe01e09f3ce04b03",
    "vortex": "89d6bbd412a328ea",
    "zscore": "f13d4d992ca85e24",
}


def test_well_formed_data_is_bit_identical(healthy: list) -> None:
    """THE OPPOSITE CONTROL, and it is as binding as the abstentions.

    These twelve digests were taken from the tree BEFORE the repair. Any
    movement means a healthy vote changed and the repair over-reached.
    The digest reads direction, confidence, weight and every detail
    field, so a change in the last bit of any of them fails this test --
    proved by adding one ULP to a single confidence, which moved that
    indicator's digest and left the other eleven untouched.
    """
    summary = VotingEngine().compute_all(healthy, "1h")
    got = {s.indicator: _hash_signal(s) for s in summary.signals}
    assert got == EXPECTED_HEALTHY_HASHES
    assert len(got) == 12
