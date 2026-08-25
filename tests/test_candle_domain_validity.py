"""The candle boundary refuses a value that is not a price.

WHY THIS FILE EXISTS. ``candles_from_raw`` is the single conversion
point every live indicator consumer passes through, and it accepted
anything: measured on the promoted tree before this change,
``close = 0.0``, ``close = -5.0``, ``close = nan`` and even
``close = 'abc'`` all reached the twelve wired indicators. Its own
comment claimed it failed loudly on malformed data. It did not; it
raised only on a short row.

WHAT THAT COST. One ``close = 0.0`` in a 100-bar window moved 10 of the
12 indicators. Four of them -- macd, stochastic_rsi, supertrend, rsi --
were still wrong 60 bars later. Slingshot turned the same bar into
BULLISH at confidence 1.0000, because ``penetration * 8`` receives
``(low - close) / low`` and a close of zero makes that exactly 1.0.

WHY THE REPAIR IS A DOMAIN AND NOT A COEFFICIENT. No published source
defines a snapback confidence scale, so re-tuning ``* 8`` would invent
one -- and it would still leave the other nine indicators exposed to
the same tick. The constraints pinned below are instead the DEFINITION
of an OHLC bar. None of them is calibrated.

THE TWO SIDES. Refusing too much is the worse failure: a screen that
kills real signal costs more than the tick it blocks. So the refusal
tests below are paired with acceptance tests for sub-cent prices, a
zero-volume bar, a flat window and a genuine deep sell-off.
"""

from __future__ import annotations

import pytest

from src.trading.ta_engine import (
    CandleDomainError,
    SignalDirection,
    SlingshotIndicator,
    candles_from_raw,
)

BASE_TS = 1_776_778_500_000
STEP_MS = 3_600_000

# The bad-tick vote the old boundary produced. Pinned so a regression is
# measured against the real number, not against the word "high".
OLD_BAD_TICK_CONFIDENCE = 1.0

# Slingshot's snapback window is ``range(-5, -1)``, i.e. j in -5..-2, so
# the reachable depths are bars_back 1..4. Four bars, not five.
REACHABLE_BARS_BACK = (1, 2, 3, 4)


def _bar(
    ts: int, open_px: float, close_px: float, pad: float = 0.004, volume: float = 1000.0
) -> list[float]:
    """Build one self-consistent OHLCV row: low <= open, close <= high."""
    high = max(open_px, close_px) * (1.0 + pad)
    low = min(open_px, close_px) * (1.0 - pad)
    return [ts, open_px, high, low, close_px, volume]


def _rising_tape(n: int, seed: int = 12345) -> list[list[float]]:
    """Build a quiet rising tape with a deterministic LCG.

    No ``random`` import: the generator is written out so the tape is
    reproducible and carries no cryptographic-source finding.
    """
    state = seed
    rows: list[list[float]] = []
    price = 100.0
    for _ in range(n):
        state = (1103515245 * state + 12345) % (2**31)
        wobble = ((state / (2**31)) - 0.5) * 0.004
        open_px = price
        price = price * (1.0 + 0.001 + wobble)
        rows.append(_bar(BASE_TS + len(rows) * STEP_MS, open_px, price))
    return rows


def _selloff_tape(drop: float, recovery: float, n_pre: int = 60) -> list[list[float]]:
    """Build a quiet tape, one sharp sell-off bar, then a recovery bar.

    Every bar stays self-consistent, so the whole tape is inside the
    closed domain: this is real market shape, not a corrupt tick.
    """
    rows = _rising_tape(n_pre)
    price = rows[-1][4]
    open_px = price
    price = price * (1.0 - drop)
    rows.append(_bar(BASE_TS + len(rows) * STEP_MS, open_px, price))
    open_px = price
    price = price * (1.0 + recovery)
    rows.append(_bar(BASE_TS + len(rows) * STEP_MS, open_px, price))
    return rows


# ---------------------------------------------------------------------
# REFUSED: values that are not prices
# ---------------------------------------------------------------------
@pytest.mark.parametrize(
    "row",
    [
        pytest.param([BASE_TS, 100.0, 101.0, 99.0, 0.0, 10.0], id="close-zero"),
        pytest.param([BASE_TS, 100.0, 101.0, 99.0, 1e-12, 10.0], id="close-tiny"),
        pytest.param([BASE_TS, 100.0, 101.0, 99.0, -5.0, 10.0], id="close-negative"),
        pytest.param([BASE_TS, 100.0, 101.0, 99.0, float("nan"), 10.0], id="close-nan"),
        pytest.param([BASE_TS, 100.0, 101.0, 99.0, float("inf"), 10.0], id="close-inf"),
        pytest.param([BASE_TS, 100.0, 101.0, 99.0, "abc", 10.0], id="close-string"),
        pytest.param([BASE_TS, 100.0, 101.0, 99.0, True, 10.0], id="close-bool"),
        pytest.param([BASE_TS, 0.0, 101.0, 99.0, 100.0, 10.0], id="open-zero"),
        pytest.param([BASE_TS, 100.0, 0.0, 99.0, 100.0, 10.0], id="high-zero"),
        pytest.param([BASE_TS, 100.0, 101.0, 0.0, 100.0, 10.0], id="low-zero"),
        pytest.param([BASE_TS, 100.0, 99.0, 101.0, 100.0, 10.0], id="high-below-low"),
        pytest.param([BASE_TS, 100.0, 101.0, 99.0, 500.0, 10.0], id="close-above-high"),
        pytest.param([BASE_TS, 50.0, 101.0, 99.0, 100.0, 10.0], id="open-below-low"),
        pytest.param([BASE_TS, 100.0, 101.0, 99.0, 100.0, -1.0], id="volume-negative"),
        pytest.param(
            [BASE_TS, 100.0, 101.0, 99.0, 100.0, float("nan")], id="volume-nan"
        ),
        pytest.param(
            [float("nan"), 100.0, 101.0, 99.0, 100.0, 10.0], id="timestamp-nan"
        ),
    ],
)
def test_row_outside_the_domain_is_refused(row: list[object]) -> None:
    """Refuse a non-price before it can become a Candle.

    If this goes green after the screen is removed, the boundary is
    open again and every indicator downstream is reading garbage.
    """
    with pytest.raises(CandleDomainError):
        candles_from_raw([row])


def test_tiny_close_is_refused_for_the_right_reason() -> None:
    """Prove a ``close == 0.0`` equality check would NOT close this.

    1e-12 drives ``(low - close) / low`` to ~1.0 just as a zero does, so
    an equality guard leaves the maximum-confidence vote reachable.
    What refuses it is the bar's own range, not its distance from zero.
    """
    row = [BASE_TS, 100.0, 101.0, 99.0, 1e-12, 10.0]
    with pytest.raises(CandleDomainError, match="outside"):
        candles_from_raw([row])


def test_short_row_still_raises_index_error() -> None:
    """Preserve the behaviour a structural malformation already had."""
    with pytest.raises(IndexError):
        candles_from_raw([[BASE_TS, 100.0, 101.0]])


# ---------------------------------------------------------------------
# ACCEPTED: real market shapes the screen must not kill
# ---------------------------------------------------------------------
@pytest.mark.parametrize(
    "row",
    [
        pytest.param([BASE_TS, 100.0, 101.0, 99.0, 100.5, 10.0], id="ordinary-bar"),
        pytest.param([BASE_TS, 1e-8, 1.1e-8, 0.9e-8, 1.05e-8, 10.0], id="sub-cent"),
        pytest.param([BASE_TS, 100.0, 101.0, 99.0, 100.0, 0.0], id="zero-volume"),
        pytest.param([BASE_TS, 100.0, 100.0, 100.0, 100.0, 10.0], id="flat-bar"),
        pytest.param([BASE_TS, 100.0, 101.0, 99.0, 101.0, 10.0], id="close-at-high"),
        pytest.param([BASE_TS, 100.0, 101.0, 99.0, 99.0, 10.0], id="close-at-low"),
        pytest.param([BASE_TS, 100, 101, 99, 100, 10], id="integer-fields"),
    ],
)
def test_real_market_shape_is_accepted(row: list[float]) -> None:
    """Accept every legitimate market state.

    Refusing too much is the worse failure. A red here means the screen
    is killing real data -- sub-cent prices, a dead-volume bar and a
    flat window are all states a live feed produces.
    """
    candles = candles_from_raw([row])
    assert len(candles) == 1
    assert isinstance(candles[0].close, float)


def test_self_consistent_spike_is_deliberately_not_refused() -> None:
    """Pin the limit of this screen so it cannot change silently.

    A bar that lifts close AND high together is internally consistent.
    Calling it invalid needs a neighbour-relative threshold, and no
    published source supplies one. This screen does not invent it.
    """
    row = [BASE_TS, 100.0, 101_000.0, 99.0, 100_000.0, 10.0]
    assert len(candles_from_raw([row])) == 1


# ---------------------------------------------------------------------
# THE DEFECT: the corrupt tick can no longer cast a maximum vote
# ---------------------------------------------------------------------
@pytest.mark.parametrize("bars_back", REACHABLE_BARS_BACK)
def test_zero_close_cannot_reach_slingshot_at_any_depth(bars_back: int) -> None:
    """Refuse the bad tick at the boundary, so no vote is cast.

    Before this change each of these depths produced BULLISH at
    confidence 1.0000 from a NEUTRAL 0.0000 control. A green here with
    the screen removed means the maximum-confidence bad-tick vote is
    live again on every bot.
    """
    rows = _rising_tape(100)
    rows[-1 - bars_back][4] = 0.0
    with pytest.raises(CandleDomainError):
        candles_from_raw(rows)


@pytest.mark.parametrize("bars_back", REACHABLE_BARS_BACK)
def test_clean_control_tape_is_quiet_at_the_same_depths(bars_back: int) -> None:
    """Show the control arm: the tape is otherwise silent.

    Without this, the test above could pass on a tape that was never
    going to fire, and would be measuring nothing.
    """
    rows = _rising_tape(100 - bars_back)
    signal = SlingshotIndicator().compute(candles_from_raw(rows), "1h")
    assert signal.direction is SignalDirection.NEUTRAL
    assert signal.confidence == 0.0


def test_bad_tick_vote_is_no_longer_reachable() -> None:
    """State the whole point as one number.

    The old boundary let a single corrupt bar produce a weight-1.0 vote
    at confidence 1.0 -- a full 1.0 of net_score and 1.0/11.7 of
    consensus confidence, on every bot.
    """
    rows = _rising_tape(100)
    rows[-3][4] = 0.0
    with pytest.raises(CandleDomainError):
        candles_from_raw(rows)
    assert OLD_BAD_TICK_CONFIDENCE == 1.0


# ---------------------------------------------------------------------
# THE OPPOSITE FAILURE: a real deep penetration must still score
# ---------------------------------------------------------------------
def test_genuine_sharp_selloff_still_scores_a_strong_snapback() -> None:
    """Keep a real reversal scoring.

    A guard that kills real signal is worse than the tick it blocks. A
    3% single-bar sell-off through the lower band, then a recovery bar
    back inside it, is exactly the reversal the snapback exists to
    catch. It is well-formed, so the screen must not touch it.
    """
    rows = _selloff_tape(drop=0.03, recovery=0.02)
    signal = SlingshotIndicator().compute(candles_from_raw(rows), "1h")
    assert signal.direction is SignalDirection.BULLISH
    assert signal.details.get("slingshot_type") == "bullish_snapback"
    assert signal.confidence == pytest.approx(0.6045, abs=5e-4)


def test_snapback_confidence_still_orders_by_depth() -> None:
    """Keep the confidence carrying information about depth.

    Measured on this tape, the snapback branch runs from 0.5591 at a
    2.2% break to 0.6361 at 3.6%; past ~3.8% the squeeze branch takes
    precedence and the type changes. Both depths below stay inside the
    snapback branch so the comparison is between like and like.
    """
    deep = SlingshotIndicator().compute(
        candles_from_raw(_selloff_tape(drop=0.034, recovery=0.02)), "1h"
    )
    shallow = SlingshotIndicator().compute(
        candles_from_raw(_selloff_tape(drop=0.024, recovery=0.02)), "1h"
    )
    assert deep.details.get("slingshot_type") == "bullish_snapback"
    assert shallow.details.get("slingshot_type") == "bullish_snapback"
    assert deep.direction is SignalDirection.BULLISH
    assert shallow.direction is SignalDirection.BULLISH
    assert deep.confidence > shallow.confidence
