"""The emitter contract: expected + actual in one immutable record.

Operator directive 2026-08-08: emitters must produce "a standardized output
format that you can read i.e. name, location, expected result, actual result",
and "emitter data is not allowed to be mutated after retrieval."

THE POSITIVE CONTROL FOR THE WHOLE DESIGN is
`TestItCatchesTheLieItWasBuiltFor` — it reproduces the per-candle-TA claim in
miniature and shows the record set falsifies it. A contract framework that
cannot catch the failure it was commissioned for is theatre, which is the one
thing the operator said he would not accept.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.signal_contract import (  # noqa: E402
    Signal,
    SignalSink,
    emit,
    get_sink,
    read_records,
    set_sink,
)


@pytest.fixture
def sink(tmp_path):
    s = SignalSink(path=tmp_path / "signals.jsonl", flush_every=1000)
    set_sink(s)
    yield s
    set_sink(None)


class TestTheRecordShape:
    """name / location / expected / actual — the operator's four, plus the
    fields needed to order and slice them."""

    def test_it_carries_all_four(self, sink):
        s = sink.emit(
            "ta.07.003.postcondition.computed",
            actual=40,
            expected=1800,
            context={"bot_id": "c8e5c5db"},
        )
        assert s.name == "ta.07.003.postcondition.computed"
        assert s.expected == 1800
        assert s.actual == 40
        assert s.site.startswith("test_signal_contract.py:")

    def test_the_verdict_is_derived_when_not_given(self, sink):
        assert sink.emit("x", actual=5, expected=5).ok is True
        assert sink.emit("x", actual=4, expected=5).ok is False

    def test_an_observation_with_no_expectation_is_unjudged(self, sink):
        """Distinct from a passing check. Recording that something happened,
        asserting nothing about it, is legitimate — and must not be counted
        as a pass."""
        s = sink.emit("candle.stepped", actual=1)
        assert s.expected is None
        assert s.ok is None

    def test_location_is_captured_automatically(self, sink):
        """A hand-passed location is one more thing that can be wrong, and it
        rots silently when code moves."""
        a = sink.emit("a", actual=1)
        b = sink.emit("b", actual=1)
        assert a.site != b.site
        assert a.site.split(":")[1].isdigit()

    def test_sequence_is_monotonic(self, sink):
        """Total order independent of clock resolution — two records in the
        same millisecond must still be ordered."""
        seqs = [sink.emit("x", actual=i).seq for i in range(50)]
        assert seqs == sorted(seqs)
        assert len(set(seqs)) == 50


class TestItEmitsOnTheSuccessPath:
    """THE departure from Design by Contract / RV / icontract, all of which
    are failure-triggered. Silence must not be ambiguous."""

    def test_a_satisfied_expectation_is_recorded(self, sink):
        sink.emit("ta.07.003.postcondition.computed", actual=100, expected=100)
        assert len(sink.records("ta.07.003.postcondition.computed")) == 1

    def test_ran_correctly_is_distinguishable_from_never_ran(self, sink):
        """The exact ambiguity that let 'per-candle TA ran' stand. Under a
        failure-triggered framework both of these produce zero records."""
        sink.emit("ta.07.003.postcondition.computed", actual=100, expected=100)
        ran_ok = sink.count("ta.07.003.postcondition.computed")

        s2 = SignalSink(flush_every=1000)  # nothing emitted at all
        never_ran = s2.count("ta.07.003.postcondition.computed")

        assert ran_ok == 1
        assert never_ran == 0
        assert ran_ok != never_ran


class TestItCatchesTheLieItWasBuiltFor:
    """POSITIVE CONTROL FOR THE ENTIRE DESIGN.

    Reproduces the measured Nuclear defect in miniature: a tick loop whose
    TA is throttled to 1-in-12 by the read-rate skip in
    `ScrummingBot.tick` (`src/trading/scrumming_bot.py`), against a
    claim that TA runs every tick.
    """

    def test_the_record_set_falsifies_per_candle_ta(self, sink):
        CANDLES, SKIP = 120, 12
        counter = 0
        for _ in range(CANDLES):
            counter += 1
            sink.emit("tick.entered", actual=1)  # what bots_ticked counted
            if counter < SKIP:
                continue  # the throttle
            counter = 0
            sink.emit("ta.07.003.postcondition.computed", actual=1)

        ticks = sink.count("tick.entered")
        computes = sink.count("ta.07.003.postcondition.computed")

        assert ticks == CANDLES
        assert computes == CANDLES // SKIP
        assert computes < ticks, (
            "the record set cannot distinguish per-candle TA from throttled "
            "TA; this design does not solve the problem it exists for"
        )

    def test_tick_entries_alone_would_have_hidden_it(self, sink):
        """Why the old instrumentation failed: `bots_ticked` counted tick
        ENTRIES, so an early return looked identical to a full evaluation."""
        for _ in range(120):
            sink.emit("tick.entered", actual=1)
        assert sink.count("tick.entered") == 120
        assert sink.count("ta.07.003.postcondition.computed") == 0


class TestDataIsNotMutableAfterRetrieval:
    """Operator's hard requirement, enforced by construction."""

    def test_a_record_cannot_be_edited(self, sink):
        s = sink.emit("x", actual=1, expected=1)
        with pytest.raises(Exception):
            s.actual = 999  # frozen dataclass

    def test_retrieval_returns_an_immutable_collection(self, sink):
        sink.emit("x", actual=1)
        got = sink.records()
        assert isinstance(got, tuple)
        with pytest.raises(AttributeError):
            got.append(Signal(name="forged", site="?", actual=0))

    def test_a_consumer_cannot_shrink_the_captured_set(self, sink):
        sink.emit("x", actual=1)
        sink.records()  # a caller takes a copy
        assert sink.count("x") == 1

    def test_mutating_the_caller_context_does_not_alter_the_record(self, sink):
        """The EventBus hazard this design avoids: `Event.data` is handed to
        subscribers by reference, so any of them can rewrite it."""
        ctx = {"bot_id": "c8e5c5db"}
        s = sink.emit("x", actual=1, context=ctx)
        ctx["bot_id"] = "TAMPERED"
        assert s.context["bot_id"] == "c8e5c5db"


class TestTheEmitPathDoesNoIO:
    """`EventBus.emit` runs subscribers synchronously on the caller's thread,
    and the sim ticks on the loop main.py pumps from the Qt GUI thread. Disk
    on the emit path would block the GUI every signal."""

    def test_nothing_is_written_before_the_flush_threshold(self, tmp_path):
        p = tmp_path / "s.jsonl"
        s = SignalSink(path=p, flush_every=50)
        for _ in range(49):
            s.emit("x", actual=1)
        assert not p.exists()

    def test_the_buffer_flushes_at_the_threshold(self, tmp_path):
        p = tmp_path / "s.jsonl"
        s = SignalSink(path=p, flush_every=50)
        for _ in range(50):
            s.emit("x", actual=1)
        assert p.exists()
        assert len(p.read_text(encoding="utf-8").strip().splitlines()) == 50

    def test_emit_never_raises_on_an_unwritable_sink(self, tmp_path):
        """Instrumentation must never take the application down, and a lost
        write must be COUNTED so a partial record set announces itself.

        The path is a DIRECTORY, so opening it for append raises OSError.
        An earlier version used a non-existent nested path, which does not
        fail — the sink mkdir(parents=True)s its own parent.
        """
        d = tmp_path / "is_a_dir.jsonl"
        d.mkdir()
        s = SignalSink(path=d, flush_every=1)
        assert s.emit("x", actual=1) is not None  # emit still succeeds
        assert s.health()["dropped"] >= 1  # and the loss is visible


class TestStorageIsAppendOnly:
    def test_a_second_flush_appends_rather_than_rewrites(self, tmp_path):
        p = tmp_path / "s.jsonl"
        s = SignalSink(path=p, flush_every=2)
        for _ in range(2):
            s.emit("a", actual=1)
        first = p.read_text(encoding="utf-8")
        for _ in range(2):
            s.emit("b", actual=1)
        after = p.read_text(encoding="utf-8")
        assert after.startswith(first)
        assert len(after.splitlines()) == 4

    def test_records_round_trip_from_disk(self, tmp_path):
        """EVERY field, not a chosen few.

        This used to check four fields, and `module`, `kind` and `count`
        were silently dropped by the reader underneath it. Comparing the
        whole record is the same invariant asserted so that no field can
        go missing again.
        """
        p = tmp_path / "s.jsonl"
        s = SignalSink(path=p, flush_every=1)
        s.emit(
            "ta.07.003.postcondition.computed",
            actual=40,
            expected=1800,
            context={"bot_id": "c8e5c5db"},
            count=7,
        )
        written = s.records()[0]
        back = read_records(p)
        assert len(back) == 1
        assert back[0] == written
        assert back[0].expected == 1800
        assert back[0].actual == 40
        assert back[0].ok is False
        assert back[0].context["bot_id"] == "c8e5c5db"
        assert back[0].count == 7

    def test_a_sample_does_not_come_back_as_a_check(self, tmp_path):
        """The control for the round trip above.

        A sample asserts nothing, and its verdict column must stay
        blank. The reader used to rebuild every record as a `check`, so
        this line changed meaning between being written and being read.
        """
        p = tmp_path / "s.jsonl"
        s = SignalSink(path=p, flush_every=1)
        s.emit("sim.06.014.event.log.line", actual="hello")
        written = s.records()[0]
        assert written.kind == "sample"
        back = read_records(p)
        assert back[0].kind == "sample"
        assert back[0].module == written.module
        assert "----" in back[0].message()

    def test_a_list_payload_comes_back_as_the_same_container(self, tmp_path):
        """`emit` stores a list as a tuple. A plain list read back would
        not compare equal to what was written."""
        p = tmp_path / "s.jsonl"
        s = SignalSink(path=p, flush_every=1)
        s.emit("ytd.10.003.gauge.per_symbol_counts", actual=[1, 2, 3])
        back = read_records(p)
        assert back[0].actual == (1, 2, 3)
        assert back[0] == s.records()[0]

    def test_every_line_is_valid_json(self, tmp_path):
        p = tmp_path / "s.jsonl"
        s = SignalSink(path=p, flush_every=1)
        s.emit("x", actual={"nested": [1, 2]}, expected=None)
        s.emit("y", actual=object())  # unserialisable -> repr
        for line in p.read_text(encoding="utf-8").strip().splitlines():
            json.loads(line)


class TestTheConnectionLayer:
    """Module-level `emit` — a call site needs no reference to anything."""

    def test_emit_reaches_the_installed_sink(self, sink):
        emit("x", actual=1, expected=1)
        assert sink.count("x") == 1

    def test_emit_is_a_noop_with_no_sink(self):
        """Instrumentation can live on a hot path and cost nothing when
        nobody is collecting."""
        set_sink(None)
        assert emit("x", actual=1) is None

    def test_the_site_is_the_callers_not_the_modules(self, sink):
        emit("x", actual=1)
        assert sink.records("x")[0].site.startswith("test_signal_contract.py:")

    def test_the_sink_is_swappable(self, tmp_path):
        a = SignalSink(flush_every=1000)
        b = SignalSink(flush_every=1000)
        set_sink(a)
        emit("x", actual=1)
        set_sink(b)
        emit("x", actual=1)
        assert a.count("x") == 1 and b.count("x") == 1
        assert get_sink() is b
        set_sink(None)


class TestTheSinkReportsItsOwnHealth:
    """A partial record set must announce itself rather than read as
    complete — the same silence problem, one level up."""

    def test_health_reports_what_was_emitted(self, sink):
        for _ in range(5):
            sink.emit("x", actual=1)
        assert sink.health()["emitted"] == 5
        assert sink.health()["dropped"] == 0

    def test_stats_separate_pass_fail_and_unjudged(self, sink):
        sink.emit("x", actual=1, expected=1)
        sink.emit("x", actual=2, expected=1)
        sink.emit("x", actual=3)
        st = sink.stats()["x"]
        assert (st["n"], st["ok"], st["bad"], st["unjudged"]) == (3, 1, 1, 1)

    def test_violations_are_retrievable(self, sink):
        sink.emit("x", actual=1, expected=1)
        sink.emit("y", actual=2, expected=1)
        v = sink.violations()
        assert len(v) == 1 and v[0].name == "y"


class TestTheHandlerSortsBySubsystem:
    """The pins are all wired to one handler, and the handler parses what
    it reads by application subsystem — the operator's model, 2026-08-10.
    """

    def test_records_are_grouped_by_the_name_before_the_first_dot(self, sink):
        sink.emit("sim.06.004.counter.trades_fired", actual=3)
        sink.emit("sim.06.001.postcondition.candles_stepped", actual=99)
        sink.emit("ta.07.003.postcondition.computed", actual=1)
        groups = sink.by_subsystem()
        assert sorted(groups) == ["sim", "ta"]
        assert len(groups["sim"]) == 2
        assert len(groups["ta"]) == 1

    def test_one_subsystem_can_be_asked_for_on_its_own(self, sink):
        sink.emit("sim.06.004.counter.trades_fired", actual=3)
        sink.emit("ta.07.003.postcondition.computed", actual=1)
        only = sink.by_subsystem("ta")
        assert list(only) == ["ta"]
        assert only["ta"][0].name == "ta.07.003.postcondition.computed"

    def test_a_name_with_no_dot_still_lands_in_a_bucket(self, sink):
        """The control: no record may fall out of the grouping. A
        grouping that drops what it cannot parse reports a smaller world
        than the one it measured."""
        sink.emit("orphan", actual=1)
        groups = sink.by_subsystem()
        assert groups["orphan"][0].name == "orphan"
        assert sum(len(v) for v in groups.values()) == sink.count()

    def test_the_grouping_keeps_emission_order(self, sink):
        for i in range(4):
            sink.emit("sim.06.014.event.log.line", actual=i)
        assert [r.actual for r in sink.by_subsystem()["sim"]] == [0, 1, 2, 3]
