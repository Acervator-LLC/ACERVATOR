"""S1, YTD half — "Load isolated sim of all live bots via YTD + bot_state."

The bot_state half emits (test_feature1_fleet_load_emitters.py). The YTD half
emitted nothing: trades were fetched into panel memory, used to build anchors,
and lost when the panel died. The only trace was a `logger.info`.

WHY IT MATTERS MORE THAN THE OTHER HALF. YTD is the operator's REAL live trade
history, and it is the REFERENCE DATASET. S3 is defined as "feed the same tick
sequence to sim and diff gate.log outputs" — checkable only against these
trades. It is also the defence against a self-consistent lie: an expectation
derived from live behaviour cannot be quietly written to match a sim bug.

These tests drive the emitters directly rather than through Qt. The panel needs
a bot_manager, an async loop and a live exchange to fetch; the EMITTER contract
is what is under test here, not the network call.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.signal_contract import SignalSink, emit, set_sink  # noqa: E402

FLEET = {"BTC/USD", "ETH/USD", "SOL/USD"}


@pytest.fixture
def sink():
    s = SignalSink(flush_every=10_000)
    set_sink(s)
    yield s
    set_sink(None)


def _fetch(sink, by_symbol, since_ts=1.0):
    """Reproduce the emit block at fleet_replay_panel.py's _do_fetch."""
    total = sum(by_symbol.values())
    emit(
        "ytd.10.001.gauge.trades_fetched",
        actual=total,
        context={"since_ts": since_ts, "symbols": len(by_symbol)},
    )
    covered = sorted(set(by_symbol) & FLEET)
    emit(
        "ytd.10.002.postcondition.fleet_symbol_coverage",
        actual=covered,
        expected=sorted(FLEET),
        context={"uncovered": sorted(FLEET - set(by_symbol))},
    )
    emit("ytd.10.003.gauge.per_symbol_counts", actual=dict(sorted(by_symbol.items())))


class TestTheEmittersFire:
    def test_a_fetch_records_something(self, sink):
        """POSITIVE CONTROL — the prior state of this path was silence."""
        _fetch(sink, {"BTC/USD": 10})
        assert sink.names()

    def test_all_three_signals_fire_once(self, sink):
        _fetch(sink, {"BTC/USD": 10, "ETH/USD": 5})
        for n in (
            "ytd.10.001.gauge.trades_fetched",
            "ytd.10.002.postcondition.fleet_symbol_coverage",
            "ytd.10.003.gauge.per_symbol_counts",
        ):
            assert sink.count(n) == 1


class TestTradeCountIsRecorded:
    def test_the_total_is_the_actual(self, sink):
        _fetch(sink, {"BTC/USD": 10, "ETH/USD": 5})
        assert sink.records("ytd.10.001.gauge.trades_fetched")[0].actual == 15

    def test_a_zero_fetch_is_recorded_not_silent(self, sink):
        """The failure this most needs to catch. A fetch that returned
        nothing must leave a record saying so — under the old logger.info
        an empty fetch and a never-run fetch were the same."""
        _fetch(sink, {})
        r = sink.records("ytd.10.001.gauge.trades_fetched")[0]
        assert r.actual == 0
        assert sink.count("ytd.10.001.gauge.trades_fetched") == 1

    def test_the_window_is_recorded(self, sink):
        """Which window was fetched is part of what the reference IS."""
        _fetch(sink, {"BTC/USD": 1}, since_ts=1735689600.0)
        assert (
            sink.records("ytd.10.001.gauge.trades_fetched")[0].context["since_ts"]
            == 1735689600.0
        )


class TestCoverageIsJudgedAgainstTheFleet:
    """A fleet symbol with no YTD trades has no reference to diff against,
    so S3 cannot speak for that bot. That must be visible."""

    def test_full_coverage_passes(self, sink):
        _fetch(sink, {s: 3 for s in FLEET})
        r = sink.records("ytd.10.002.postcondition.fleet_symbol_coverage")[0]
        assert r.ok is True
        assert r.context["uncovered"] == ()  # frozen empty

    def test_partial_coverage_fails_and_names_the_gap(self, sink):
        _fetch(sink, {"BTC/USD": 3})
        r = sink.records("ytd.10.002.postcondition.fleet_symbol_coverage")[0]
        assert r.ok is False, "a partial reference must not read as success"
        assert set(r.context["uncovered"]) == {"ETH/USD", "SOL/USD"}

    def test_extra_symbols_do_not_count_as_coverage(self, sink):
        """Trades on a symbol outside the fleet are not evidence for it."""
        _fetch(sink, {"DOGE/USD": 99})
        r = sink.records("ytd.10.002.postcondition.fleet_symbol_coverage")[0]
        assert r.actual == ()  # frozen empty
        assert r.ok is False


class TestThePerSymbolBreakdownSurvives:
    def test_counts_are_retrievable_per_symbol(self, sink):
        _fetch(sink, {"BTC/USD": 10, "ETH/USD": 5})
        assert sink.records("ytd.10.003.gauge.per_symbol_counts")[0].actual == {
            "BTC/USD": 10,
            "ETH/USD": 5,
        }

    def test_it_is_unjudged(self, sink):
        """A breakdown asserts nothing — recording it is not a pass."""
        _fetch(sink, {"BTC/USD": 1})
        assert sink.records("ytd.10.003.gauge.per_symbol_counts")[0].ok is None


class TestRetrievedDataIsNotMutable:
    def test_the_record_is_frozen(self, sink):
        _fetch(sink, {"BTC/USD": 1})
        r = sink.records("ytd.10.001.gauge.trades_fetched")[0]
        with pytest.raises(Exception):
            r.actual = 999

    def test_mutating_the_counts_dict_afterwards_changes_nothing(self, sink):
        counts = {"BTC/USD": 10}
        _fetch(sink, counts)
        counts["BTC/USD"] = 999
        assert (
            sink.records("ytd.10.003.gauge.per_symbol_counts")[0].actual["BTC/USD"]
            == 10
        )
