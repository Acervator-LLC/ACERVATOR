"""A confidence must be a confidence: inside [0, 1], always.

WHAT WAS WRONG. `SlingshotIndicator.compute` built

    squeeze_conf = min(1.0, squeeze_depth * 3 + expansion_rate * 2 + 0.3)

which clamps the ceiling and leaves the floor open. `expansion_rate` is
signed -- `(curr_bw - prev2_bw) / prev2_bw`, negative whenever the
Bollinger bandwidth is contracting -- so the sum goes below zero and the
indicator reported a NEGATIVE confidence. Measured on a 3-bot /
400-candle replay of the operator's real fleet: 30 of 1173 records, low
-0.2722.

WHY IT MATTERS EVEN THOUGH IT WAS LATENT. `confidence` only takes this
value on the `squeeze_bull` / `squeeze_bear` branches, and every firing
in that sample had a positive sum, so no vote was affected. But
`Signal.weighted_score` is `direction.value * confidence * weight` and
`VotingEngine._aggregate` adds `abs(ws)` to the winning side. A negative
confidence therefore would not vote WEAKLY -- the sign is discarded and
it votes with its full magnitude on the side it was meant to doubt.

`squeeze_depth` on the line above already guards its own numerator with
`max(0.0, ...)`. This is that same guard, missing one line down.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading.ta_engine import Candle, SlingshotIndicator  # noqa: E402


def _contracting(n=200, start=100.0):
    """Bandwidth shrinking hard -- drives expansion_rate negative, which
    is the input that pushed the sum below zero."""
    out = []
    for i in range(n):
        amp = max(0.02, 8.0 * (1.0 - i / n) ** 3)
        c = start + math.sin(i / 2.0) * amp
        out.append(
            Candle(
                1_700_000_000_000 + i * 300_000,
                c,
                c + amp * 0.5,
                c - amp * 0.5,
                c,
                100.0,
            )
        )
    return out


def _expanding(n=200, start=100.0):
    out = []
    for i in range(n):
        amp = 0.05 + 6.0 * (i / n) ** 3
        c = start + math.sin(i / 2.0) * amp
        out.append(
            Candle(
                1_700_000_000_000 + i * 300_000,
                c,
                c + amp * 0.5,
                c - amp * 0.5,
                c,
                100.0,
            )
        )
    return out


def _flat(n=200, start=100.0):
    """Zero volatility -- exercises the epsilon-guarded divisions."""
    return [
        Candle(1_700_000_000_000 + i * 300_000, start, start, start, start, 100.0)
        for i in range(n)
    ]


class TestConfidenceStaysInsideZeroToOne:
    def test_contracting_bands(self):
        d = SlingshotIndicator().compute(_contracting()).details
        assert 0.0 <= d["squeeze_conf"] <= 1.0, d["squeeze_conf"]

    def test_expanding_bands(self):
        d = SlingshotIndicator().compute(_expanding()).details
        assert 0.0 <= d["squeeze_conf"] <= 1.0, d["squeeze_conf"]

    def test_flat_market(self):
        """RESTATED, and STRENGTHENED, when the zero-denominator repair
        landed. It previously read `details["squeeze_conf"]` on a flat
        market and asked only that the clamp had held it inside [0, 1].

        On a flat market there is no volatility: the Keltner range and
        both Bollinger bandwidths are EXACTLY zero, and `squeeze_depth`,
        `expansion_rate` and `mom_norm` were each 0/0. The old reading
        was the clamp's output, not a measurement -- driven on a halted
        tape `mom_norm` reached 6.6e7 and the clamp reported 1.0000.

        The indicator now abstains, so there is no squeeze reading to
        bound. Asserting its ABSENCE plus an emitted confidence of
        EXACTLY 0.0 is strictly stronger than asserting a clamped value
        lay in range: 0.0 is one point of [0, 1], not an interval, and
        "no reading at all" cannot be satisfied by a saturated one.

        The original defect stays pinned. `test_the_bound_can_actually
        _fail` below is untouched, and `TestSignalConfidenceIsNever
        Negative` still drives this same flat market through the surface
        the voting engine actually consumes.
        """
        sig = SlingshotIndicator().compute(_flat())
        assert sig.confidence == 0.0, sig.confidence
        assert "squeeze_conf" not in (sig.details or {}), sig.details

    def test_snapback_confidence_too(self):
        """The bound still holds wherever the quantity EXISTS. It is not
        relaxed for any market that produces a reading -- only the flat
        market, which now produces none, is stated differently."""
        for maker in (_contracting, _expanding):
            d = SlingshotIndicator().compute(maker()).details
            assert 0.0 <= d["snapback_conf"] <= 1.0, (maker.__name__, d)

        sig = SlingshotIndicator().compute(_flat())
        assert sig.confidence == 0.0, sig.confidence
        assert "snapback_conf" not in (sig.details or {}), sig.details

    def test_the_bound_can_actually_fail(self):
        """NEGATIVE CONTROL. Reproduce the one-sided clamp on the same
        inputs the real indicator saw and show it breaches zero --
        otherwise the assertions above prove nothing about this defect.

        Values are the measured record that produced -0.0038:
        squeeze_depth 0.0, expansion_rate -0.1519.
        """
        depth, expansion = 0.0, -0.1519
        one_sided = min(1.0, depth * 3 + expansion * 2 + 0.3)
        both_sides = max(0.0, min(1.0, depth * 3 + expansion * 2 + 0.3))
        assert one_sided < 0.0, one_sided
        assert both_sides == 0.0


class TestSignalConfidenceIsNeverNegative:
    def test_emitted_signal_confidence(self):
        """The Signal the voting engine actually consumes -- not just
        the details dict."""
        for maker in (_contracting, _expanding, _flat):
            sig = SlingshotIndicator().compute(maker())
            assert 0.0 <= sig.confidence <= 1.0, (maker.__name__, sig.confidence)

    def test_weighted_score_cannot_invert(self):
        """`_aggregate` takes abs(weighted_score), so a negative
        confidence would contribute its magnitude to the side it was
        meant to doubt. With confidence >= 0 the sign of
        weighted_score is carried entirely by direction."""
        for maker in (_contracting, _expanding, _flat):
            sig = SlingshotIndicator().compute(maker())
            ws = sig.weighted_score
            assert ws == 0.0 or (ws > 0) == (sig.direction.value > 0), (
                maker.__name__,
                ws,
                sig.direction,
            )
