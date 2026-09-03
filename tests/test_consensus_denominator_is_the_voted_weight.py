"""The consensus denominator is the weight that VOTED — issue #100.

THE RULE THIS FILE PINS. ``VotingSummary.consensus_confidence`` is a
weighted arithmetic mean of each voter's signed conviction. The
published denominator of that mean is the sum of the weights of the
data points INCLUDED IN THE CALCULATION. An indicator that abstained
supplied no data point, so its weight is not one of them.

WHAT WAS WRONG. ``VotingEngine._aggregate`` divided by
``sum(s.weight for s in signals)`` — the weight of every voter the
engine ASKED. "I have too little history to have an opinion" and "I
measured, and I have no opinion" both produce ``NEUTRAL`` at confidence
0.0, so both were the same number in that denominator. They are not the
same statement, and the difference decides trades.

MEASURED over 406 stone tablets, the abstaining share of the OLD
denominator:

    bars   mean dilution   worst tablet   tablets affected
      35        34.21%         42.74%          406 / 406
      40        25.68%         42.74%          406 / 406
      60         9.44%         17.95%          406 / 406
     100         0.06%         25.64%            3 / 406
     200         0.06%         25.64%            3 / 406
     400         0.14%         41.03%            6 / 406

The live fetch is 100 candles (``ScrummingBot.tick``'s
``_get_ohlcv(..., limit=100)`` call, ``src/trading/scrumming_bot.py``),
where only a degenerate book abstains. A bot that has just spawned holds the short
tape while it makes its first decisions, and there a third of the
denominator was weight that had measured nothing.

WHAT A FAILURE HERE MEANS, per test class:
  * ABSTENTION LEAVES failing means an abstaining voter is back in the
    denominator, and consensus confidence is diluted again by a
    quantity no candle produced.
  * A MEASURED NEUTRAL STAYS failing means the repair over-reached and
    dropped a voter that DID evaluate its formula. A measured zero is a
    real term of the mean and must pull it toward zero.
  * THE VOTERS SAY SO failing means an indicator's guard stopped
    declaring its abstention, so the aggregator cannot see it however
    the aggregator is written.
  * NOBODY VOTED failing means the 0/0 case resolved to something other
    than "no consensus".

Every positive assertion is PAIRED with a control that fails when the
mechanism goes blind. A test that can only ever pass is not evidence.
"""

from __future__ import annotations

import pathlib
import sys
from typing import ClassVar

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading import ta_engine as TA  # noqa: E402


def _sig(
    name: str,
    direction: TA.SignalDirection,
    conf: float,
    weight: float,
    *,
    abstained: bool = False,
    details: dict | None = None,
) -> TA.Signal:
    return TA.Signal(
        name,
        "5m",
        direction,
        conf,
        weight,
        details if details is not None else {"x": 1},
        abstained=abstained,
    )


def _bars(n: int) -> list:
    """Build a short, admissible tape whose prices move.

    Every bar satisfies the closed OHLC domain in ``types.py``, so a
    guard that fires here fired on WARM-UP and not on a refused bar.
    """
    raw = []
    for i in range(n):
        close = 100.0 + (i % 7) * 0.5
        raw.append(
            [1775000000000 + i * 300000, close, close + 1.0, close - 1.0, close, 1000.0]
        )
    return TA.candles_from_raw(raw)


# =====================================================================
class TestAbstentionLeavesTheDenominator:
    """The positive assertion."""

    def test_an_abstaining_voter_is_not_in_the_denominator(self):
        """One bullish voter at weight 1.0, one abstainer at weight 9.0.

        The mean of the voters that voted is 0.8 / 1.0 = 0.8. Counting
        the abstainer gives 0.8 / 10.0 = 0.08 — a tenth of the
        conviction actually measured.
        """
        eng = TA.VotingEngine()
        out = eng._aggregate(
            [
                _sig("a", TA.SignalDirection.BULLISH, 0.8, 1.0),
                _sig("b", TA.SignalDirection.NEUTRAL, 0.0, 9.0, abstained=True),
            ],
            "5m",
        )
        assert out.net_score == pytest.approx(0.8)
        assert out.consensus_confidence == pytest.approx(0.8)

    def test_the_old_denominator_gave_a_different_number(self):
        """Show the two denominators disagree.

        If they agreed, the test above would be a claim about
        arithmetic and not about the repair.
        """
        signals = [
            _sig("a", TA.SignalDirection.BULLISH, 0.8, 1.0),
            _sig("b", TA.SignalDirection.NEUTRAL, 0.0, 9.0, abstained=True),
        ]
        asked = sum(s.weight for s in signals)
        voted = sum(s.weight for s in signals if not s.abstained)
        assert asked == 10.0
        assert voted == 1.0
        assert abs(0.8) / asked != abs(0.8) / voted

    def test_the_repair_can_only_raise_the_confidence(self):
        """Show the move is structural, not incidental.

        The voted weight cannot exceed the asked weight and the
        numerator is untouched, so the quotient cannot fall.
        """
        eng = TA.VotingEngine()
        base = [_sig("a", TA.SignalDirection.BEARISH, 0.5, 2.0)]
        alone = eng._aggregate(list(base), "5m").consensus_confidence
        with_abstainer = eng._aggregate(
            [*base, _sig("z", TA.SignalDirection.NEUTRAL, 0.0, 5.0, abstained=True)],
            "5m",
        ).consensus_confidence
        assert with_abstainer == pytest.approx(alone)
        assert with_abstainer >= alone


# =====================================================================
class TestAMeasuredNeutralStaysInTheDenominator:
    """The paired control on the other side.

    The repair must not turn every NEUTRAL into a non-voter. A voter
    that measured and found no direction cast a vote of zero, and a
    vote of zero belongs in a mean.
    """

    def test_a_measured_neutral_still_dilutes(self):
        eng = TA.VotingEngine()
        out = eng._aggregate(
            [
                _sig("a", TA.SignalDirection.BULLISH, 0.8, 1.0),
                _sig("b", TA.SignalDirection.NEUTRAL, 0.0, 9.0),
            ],
            "5m",
        )
        assert out.consensus_confidence == pytest.approx(0.08)

    def test_the_two_neutrals_are_now_different_numbers(self):
        """Show the two kinds of NEUTRAL no longer agree.

        Before issue #100 these two calls returned the same value.
        That equality WAS the defect, so the inequality is the test.
        """
        eng = TA.VotingEngine()
        measured = eng._aggregate(
            [
                _sig("a", TA.SignalDirection.BULLISH, 0.8, 1.0),
                _sig("b", TA.SignalDirection.NEUTRAL, 0.0, 9.0),
            ],
            "5m",
        ).consensus_confidence
        abstained = eng._aggregate(
            [
                _sig("a", TA.SignalDirection.BULLISH, 0.8, 1.0),
                _sig("b", TA.SignalDirection.NEUTRAL, 0.0, 9.0, abstained=True),
            ],
            "5m",
        ).consensus_confidence
        assert measured != abstained

    def test_the_counts_are_untouched(self):
        """Show every NEUTRAL is still counted as one.

        This repair moved the denominator and nothing else, so a
        consumer reading the counts must see what it always saw.
        """
        eng = TA.VotingEngine()
        out = eng._aggregate(
            [
                _sig("a", TA.SignalDirection.BULLISH, 0.8, 1.0),
                _sig("b", TA.SignalDirection.NEUTRAL, 0.0, 9.0, abstained=True),
                _sig("c", TA.SignalDirection.NEUTRAL, 0.0, 1.0),
            ],
            "5m",
        )
        assert out.neutral_count == 2
        assert out.bullish_count == 1
        assert out.bearish_count == 0


# =====================================================================
class TestTheVotersSaySo:
    """The aggregator can only act on a signal the voters send.

    These pin that they send it.
    """

    #: The warm-up each indicator needs before it evaluates its formula,
    #: measured on this tree. A two-bar tape is below every one of them.
    WARMUP: ClassVar[dict[str, int]] = {
        "adx": 30,
        "bollinger_bands": 20,
        "ichimoku": 79,
        "kaufman_er": 12,
        "macd": 35,
        "rsi": 15,
        "slingshot": 52,
        "stochastic_rsi": 36,
        "supertrend": 12,
        "volume": 25,
        "vortex": 15,
        "zscore": 51,
    }

    def test_every_voter_declares_its_warm_up_abstention(self):
        summary = TA.VotingEngine().compute_all(_bars(2), "5m")
        not_declared = [s.indicator for s in summary.signals if not s.abstained]
        assert (
            not_declared == []
        ), "these voters had two bars and still claimed a vote: " + repr(not_declared)

    def test_the_engine_asks_every_indicator_in_the_warm_up_table(self):
        """Show the table covers the whole panel.

        A voter added without a warm-up entry would pass the test above
        by not being read.
        """
        summary = TA.VotingEngine().compute_all(_bars(2), "5m")
        assert {s.indicator for s in summary.signals} == set(self.WARMUP)

    def test_a_voter_that_measured_does_not_declare_an_abstention(self):
        """The control on the flag itself.

        If ``abstained`` were True everywhere, the test above would
        pass on a broken flag.
        """
        summary = TA.VotingEngine().compute_all(_bars(120), "5m")
        voted = [s.indicator for s in summary.signals if not s.abstained]
        assert len(voted) == len(
            self.WARMUP
        ), "on 120 bars every voter has its warm-up; these did not vote: " + repr(
            [s.indicator for s in summary.signals if s.abstained]
        )

    def test_rsi_declares_an_abstention_its_details_would_hide(self):
        """RSI is the one voter whose abstention is invisible in output.

        ``_compute_metrics`` answers a tape shorter than ``period + 1``
        with a fabricated ``{"rsi": 50.0, ...}`` and ``rs_indeterminate``
        False, so the reading LOOKS measured. This is why ``abstained``
        is a field and not an inference from ``details == {}``: on this
        signal that inference is wrong.
        """
        sig = TA.RSIIndicator().compute(_bars(10), "5m")
        assert sig.abstained is True
        assert sig.details != {}  # the inference would miss it
        assert sig.details["rsi"] == 50.0  # unchanged: sweep item A2

    def test_rsi_stops_abstaining_once_it_has_its_period(self):
        """The paired control on the boundary itself."""
        assert TA.RSIIndicator().compute(_bars(14), "5m").abstained is True
        assert TA.RSIIndicator().compute(_bars(15), "5m").abstained is False

    @pytest.mark.parametrize("n", [2, 5, 14, 20, 30, 40, 60, 90, 120])
    def test_an_abstention_is_always_neutral_at_zero_confidence(self, n):
        """Pin the invariant the aggregator relies on and never checks.

        ``_aggregate`` keeps abstainers OUT of the denominator while
        leaving them IN the numerator loop. That is safe only while an
        abstention carries no direction: ``weighted_score`` multiplies
        by ``direction.value``, so a directional abstainer would add to
        a score it was excluded from being measured against, and the
        quotient could exceed the conviction actually cast.
        """
        for s in TA.VotingEngine().compute_all(_bars(n), "5m").signals:
            if s.abstained:
                assert s.direction is TA.SignalDirection.NEUTRAL, s.indicator
                assert s.confidence == 0.0, s.indicator
                assert s.weighted_score == 0.0, s.indicator


# =====================================================================
class TestNobodyVoted:
    """The 0/0 path.

    An undefined quantity is no vote, never an extreme of the scale —
    the rule ``tests/test_ta_engine_degenerate_abstention.py`` holds
    every division in this package to.
    """

    def test_an_engine_with_no_voters_has_no_consensus(self):
        out = TA.VotingEngine()._aggregate(
            [
                _sig("a", TA.SignalDirection.NEUTRAL, 0.0, 1.0, abstained=True),
                _sig("b", TA.SignalDirection.NEUTRAL, 0.0, 9.0, abstained=True),
            ],
            "5m",
        )
        assert out.consensus_confidence == 0.0
        assert out.net_score == 0.0
        assert out.consensus_direction is TA.SignalDirection.NEUTRAL

    def test_an_empty_signal_list_has_no_consensus(self):
        out = TA.VotingEngine()._aggregate([], "5m")
        assert out.consensus_confidence == 0.0

    def test_a_two_bar_tape_reaches_that_path_for_real(self):
        """Drive the whole engine on a real short tape.

        Not a synthetic list, so the branch is proved reachable from
        the front door.
        """
        out = TA.VotingEngine().compute_all(_bars(2), "5m")
        assert out.consensus_confidence == 0.0

    def test_one_voter_is_enough_to_have_a_consensus(self):
        """The control on the zero above.

        If it came from a guard that fires too widely, one real voter
        would return 0.0 as well.
        """
        out = TA.VotingEngine()._aggregate(
            [
                _sig("a", TA.SignalDirection.BULLISH, 0.5, 1.0),
                _sig("b", TA.SignalDirection.NEUTRAL, 0.0, 9.0, abstained=True),
            ],
            "5m",
        )
        assert out.consensus_confidence == pytest.approx(0.5)


# =====================================================================
class TestTheFlagSurvivesTheMultiTimeframeRebuild:
    """``aggregate_multi_timeframe`` does not forward its signals.

    It builds new ones with a timeframe-scaled weight. A rebuild that
    dropped ``abstained`` would leave the repair correct per timeframe
    and wrong in the multi-timeframe number the fleet reads.
    """

    def test_an_abstainer_stays_an_abstainer_across_timeframes(self):
        eng = TA.VotingEngine()
        per_tf = eng._aggregate(
            [
                _sig("a", TA.SignalDirection.BULLISH, 0.8, 1.0),
                _sig("b", TA.SignalDirection.NEUTRAL, 0.0, 9.0, abstained=True),
            ],
            "1h",
        )
        multi = eng.aggregate_multi_timeframe([per_tf])
        assert [s.abstained for s in multi.signals] == [False, True]
        # tf weight for 1h is 1.0, so the number is comparable directly
        assert multi.consensus_confidence == pytest.approx(0.8)

    def test_the_rebuild_would_otherwise_have_changed_the_number(self):
        """The control on the carry.

        Show the dropped-flag answer differs, so the assertion above is
        not true by coincidence.
        """
        eng = TA.VotingEngine()
        signals = [
            _sig("a", TA.SignalDirection.BULLISH, 0.8, 1.0),
            _sig("b", TA.SignalDirection.NEUTRAL, 0.0, 9.0, abstained=True),
        ]
        dropped = eng._aggregate(
            [
                TA.Signal(
                    s.indicator,
                    s.timeframe,
                    s.direction,
                    s.confidence,
                    s.weight,
                    s.details,
                )
                for s in signals
            ],
            "multi",
        )
        assert dropped.consensus_confidence == pytest.approx(0.08)
        assert dropped.consensus_confidence != pytest.approx(0.8)
