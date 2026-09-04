"""The squeeze flag reads bandwidths, and a bandwidth needs a closed window.

``BollingerBands.compute`` sets ``details["squeeze"]`` by comparing the
current BandWidth against the mean of the recent ones. BandWidth is
``(upper - lower) / middle``, so it exists only where the band exists,
which is from the ``period``-th close onward. ``helpers._sma_tail`` keeps
its list candle-aligned by filling the earlier indices with an average
over however many closes it has; those entries are not bands, and a
comparison that includes them is a comparison against numbers no window
produced.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading.indicators.bollinger import BollingerBands
from src.trading.indicators.types import Candle

PERIOD = BollingerBands().period


def _bar(i: int, price: float) -> Candle:
    return Candle(
        1_700_000_000_000 + i * 300_000,
        price,
        price * 1.001,
        price * 0.999,
        price,
        100.0,
    )


def _shock_tape(bars: int, seed: int, early_amp: float, switch: int) -> list[Candle]:
    """A Lehmer walk that is violent for ``switch`` bars, then quiet."""
    out, price, state = [], 1.0, seed
    for i in range(bars):
        state = (state * 48271) % 2147483647
        amp = early_amp if i < switch else 0.02
        price *= 1.0 + ((state / 2147483647) - 0.5) * amp
        out.append(_bar(i, price))
    return out


def _drift_tape(bars: int, seed: int, amp: float) -> list[Candle]:
    """A linear-congruential walk of constant amplitude."""
    out, price, state = [], 1.0, seed
    for i in range(bars):
        state = (state * 1103515245 + 12345) % 2147483648
        price *= 1.0 + ((state / 2147483648) - 0.5) * amp
        out.append(_bar(i, price))
    return out


def _contracting_tape(bars: int, seed: int) -> list[Candle]:
    """A walk that trades wide, then narrows, so a squeeze is genuine."""
    out, price, state = [], 1.0, seed
    for i in range(bars):
        state = (state * 1103515245 + 12345) % 2147483648
        amp = 0.02 if 40 <= i < 80 else 0.12
        price *= 1.0 + ((state / 2147483648) - 0.5) * amp
        out.append(_bar(i, price))
    return out


def _closed_bandwidths(candles: list[Candle]) -> list[float]:
    """Every BandWidth the indicator itself reports, one per closed window."""
    return [
        BollingerBands().compute(candles[: i + 1]).details["band_width"]
        for i in range(PERIOD - 1, len(candles))
    ]


class TestTheWidestWindowOnTheTapeIsNotASqueeze:
    """A band is not narrow beside its own history while it is the widest
    window on that history. The rule holds for every threshold in (0, 1],
    so it tests the squeeze without restating the one the code uses."""

    @pytest.mark.parametrize("early_amp", [0.30, 0.45, 0.60])
    def test_a_tape_with_one_closed_window_reports_no_squeeze(self, early_amp):
        candles = _shock_tape(PERIOD, seed=1, early_amp=early_amp, switch=3)
        bandwidths = _closed_bandwidths(candles)
        assert len(bandwidths) == 1, (
            f"a {PERIOD}-candle tape closes exactly one {PERIOD}-period window, "
            f"got {len(bandwidths)}"
        )
        signal = BollingerBands().compute(candles)
        assert signal.details["squeeze"] is False, (
            "the only closed window on the tape IS the current one, so nothing "
            f"is narrower than it; got squeeze=True at band_width="
            f"{signal.details['band_width']!r} with history {bandwidths!r}"
        )

    def test_no_tape_in_the_sweep_squeezes_on_its_widest_window(self):
        offenders = []
        for seed in range(1, 60):
            for early_amp in (0.30, 0.45, 0.60):
                for switch in (3, 5, 8):
                    candles = _shock_tape(PERIOD, seed, early_amp, switch)
                    signal = BollingerBands().compute(candles)
                    if signal.abstained:
                        continue
                    bandwidths = _closed_bandwidths(candles)
                    widest = signal.details["band_width"] >= max(bandwidths)
                    if signal.details["squeeze"] and widest:
                        offenders.append((seed, early_amp, switch))
        assert offenders == [], (
            f"{len(offenders)} tapes reported a squeeze on their widest closed "
            f"window; first ten (seed, early_amp, switch): {offenders[:10]}"
        )

    def test_the_flag_still_reports_a_squeeze_when_one_is_real(self):
        """Positive control for the two tests above."""
        candles = _contracting_tape(80, seed=2)
        signal = BollingerBands().compute(candles)
        bandwidths = _closed_bandwidths(candles)
        assert signal.details["band_width"] < max(
            bandwidths
        ), "this tape must genuinely narrow, or the control proves nothing"
        assert signal.details["squeeze"] is True, (
            "a tape that contracts must still flag a squeeze, otherwise the "
            "tests above pass on an indicator that never flags one"
        )


class TestTheHistoryStartsAtTheFirstClosedWindow:
    def test_a_thirty_candle_tape_is_judged_on_its_eleven_closed_windows(self):
        candles = _drift_tape(30, seed=21, amp=0.06)
        bandwidths = _closed_bandwidths(candles)
        assert len(bandwidths) == 30 - PERIOD + 1
        signal = BollingerBands().compute(candles)
        assert signal.details["squeeze"] is False, (
            "no closed window on this tape is wide enough to make the current "
            f"one a squeeze; history {[round(b, 6) for b in bandwidths]}, "
            f"current {signal.details['band_width']!r}"
        )
        assert signal.confidence == pytest.approx(0.72381435, abs=1e-8), (
            "the squeeze damping must not apply here; 0.7x this vote is "
            f"0.50667005, and the reported confidence is {signal.confidence!r}"
        )

    def test_history_beyond_the_last_windows_does_not_change_the_flag(self):
        """Every window the flag reads is inside the final ``2 * period - 1``
        candles, so older bars cannot move it."""
        long_tape = _contracting_tape(200, seed=5)
        short_tape = long_tape[-(2 * PERIOD - 1) :]
        assert (
            BollingerBands().compute(long_tape).details["squeeze"]
            is BollingerBands().compute(short_tape).details["squeeze"]
        ), "trimming candles no window reads changed the squeeze flag"

    def test_the_flag_takes_both_values_over_the_same_walk(self):
        """Positive control for the trim above: it compares a flag that moves,
        not two constants agreeing."""
        seen = {
            BollingerBands().compute(_contracting_tape(bars, seed=5)).details["squeeze"]
            for bars in range(45, 200, 5)
        }
        assert seen == {
            True,
            False,
        }, f"the squeeze flag never varied over this walk: {seen}"
