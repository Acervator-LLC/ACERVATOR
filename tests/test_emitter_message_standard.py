"""The emitter message standard.

Operator directives, 2026-08-08, locking the contract before more
emitters exist:

  * "module not being a field is something we can fix and should in
     order to establish the emitter message standard."
  * "render() issue will require translation to the standard emitter
     message format. we only need to know or retrieve or present data
     that can help troubleshoot issues... after release, more
     traditional coders are going to need these."
  * "expected=none is functionally useless as designed."
  * "we also need an emitter message synchronizer i think... I am
     concerned that because programs are constantly looping that some
     emitters (maybe most) will be spamming I/O messages."

FOUR THINGS, and the reasoning behind each:

MODULE. `site` carried `file:line`, so the module was implied but not
queryable -- grouping by module meant parsing a field whose line number
changes on every edit.

MESSAGE. `render()` was a debug repr that dumped the dataclass,
`mappingproxy` and all. Unreadable in a console, useless in a bug
report. `Signal.message()` is fixed-column so a wall of them scans.

KIND. `expected=None` meant BOTH "a raw observation asserting nothing"
and "somebody forgot an expectation", indistinguishable to any reader,
on 92.8% of records. `kind` declares which.

SYNCHRONISER. A per-candle emitter on a 35-bot fleet fires tens of
thousands of times per run; at that rate the file is a cost, not
evidence. `every=N` admits one record per N seconds per
(name, site, instance) and folds the rest into `count`, so nothing
vanishes silently. A FAILING check is never suppressed -- rate-limiting
the thing the network exists to catch would turn a spam control into a
blindfold.

INSTANCE, added by issue #57. `site` is `file:line`, so TWO OBJECTS OF
ONE CLASS key together and the second object's passes fold into the
first object's record: a green named one object and stood for all of
them, and an object whose emitter had STOPPED was invisible. A pin with
more than one live instance declares one -- `TestTheInstanceKey` below
drives what that changes and, as importantly, what it does not.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core import signal_contract as sc  # noqa: E402
from src.core.signal_contract import (  # noqa: E402
    Signal,
    SignalSink,
    emit,
    reset_throttle,
    set_sink,
)


def _throttle_entries() -> dict:
    """Return a COPY of the rate-limit map, read under its own lock.

    The map is private and stays private: nothing in the platform reads
    it, and a test that reached in without the lock would be reading a
    dict another thread may be writing. Its SIZE is the one property a
    test has to hold, because nothing ever prunes it.
    """
    with sc._THROTTLE_LOCK:
        return dict(sc._THROTTLE)


def _tick(name: str, value: object, expected: object, every: float,
          instance: str | None = None) -> Signal | None:
    """Emit from ONE call site.

    The throttle keys on (name, site) and on the `instance` the call
    site declares, because the same signal from two places -- or from
    two live objects on ONE line -- is two things to a reader and
    collapsing them would hide which one is firing. A loop therefore
    shares a window -- which is the case that matters -- while two
    separate `emit(...)` statements in a test do not. Every synchroniser
    test goes through here so the site is constant, as it is in the
    looping code this protects.
    """
    return emit(name, actual=value, expected=expected, every=every,
                instance=instance)


@pytest.fixture
def sink():
    s = SignalSink(flush_every=100_000)
    set_sink(s)
    reset_throttle()
    yield s
    set_sink(None)
    reset_throttle()


class TestModuleIsAField:
    def test_it_is_captured_without_being_passed(self, sink):
        emit("probe.a", actual=1, expected=1)
        assert sink.since(0)[0].module.endswith("test_emitter_message_standard")

    def test_it_can_be_overridden(self, sink):
        emit("probe.b", actual=1, expected=1, module="custom.mod")
        assert sink.since(0)[0].module == "custom.mod"

    def test_it_survives_the_json_round_trip(self, sink):
        emit("probe.c", actual=1, expected=1)
        d = json.loads(sink.since(0)[0].to_json())
        assert "module" in d and d["module"]

    def test_grouping_needs_no_string_parsing(self, sink):
        """The point of the field: group without touching `site`."""
        emit("probe.d", actual=1, expected=1, module="alpha")
        emit("probe.e", actual=2, expected=2, module="beta")
        emit("probe.f", actual=3, expected=3, module="alpha")
        by = {}
        for r in sink.since(0):
            by.setdefault(r.module, []).append(r.name)
        assert sorted(by) == ["alpha", "beta"]
        assert len(by["alpha"]) == 2


class TestTheMessageFormat:
    def test_a_pass_is_terse(self, sink):
        """A passing check's numbers are noise when hunting a failure."""
        emit("probe.pass", actual=5, expected=5)
        m = sink.since(0)[0].message()
        assert "PASS" in m
        assert "expected=" not in m

    def test_a_failure_carries_both_values(self, sink):
        emit("probe.fail", actual=4, expected=5)
        m = sink.since(0)[0].message()
        assert "FAIL" in m
        assert "expected=5" in m
        assert "actual=4" in m

    def test_a_sample_shows_its_observation(self, sink):
        emit("probe.sample", actual={"adx": 27.9})
        m = sink.since(0)[0].message()
        assert "----" in m
        assert "adx" in m

    def test_context_trails_the_line(self, sink):
        """Context says WHICH bot and WHICH candle -- the first thing
        wanted when a line is being chased."""
        emit("probe.ctx", actual=1, expected=1,
             context={"bot": "b1", "candle_ts": 1776814200000})
        m = sink.since(0)[0].message()
        assert m.rstrip().endswith("]")
        assert "bot='b1'" in m
        assert "candle_ts=1776814200000" in m

    def test_no_mappingproxy_leaks_into_the_line(self, sink):
        """The exact defect in `render()`: the reader saw the freezing
        mechanism instead of the data."""
        emit("probe.frozen", actual={"a": [1, 2]},
             context={"k": {"n": 1}})
        m = sink.since(0)[0].message()
        assert "mappingproxy" not in m

    def test_the_timestamp_is_present_and_short(self, sink):
        emit("probe.ts", actual=1, expected=1)
        m = sink.since(0)[0].message()
        assert m[:8].count(":") == 2


class TestKindIsDeclared:
    def test_an_expectation_makes_it_a_check(self, sink):
        emit("probe.k1", actual=1, expected=1)
        assert sink.since(0)[0].kind == "check"

    def test_no_expectation_makes_it_a_sample(self, sink):
        emit("probe.k2", actual=1)
        assert sink.since(0)[0].kind == "sample"

    def test_an_explicit_verdict_is_a_check(self, sink):
        """A caller that judges for itself is still checking."""
        emit("probe.k3", actual=1, ok=False)
        assert sink.since(0)[0].kind == "check"

    def test_samples_are_countable(self, sink):
        """The 92.8% figure was only knowable by inspecting `expected`.
        It is now a field."""
        emit("probe.k4", actual=1)
        emit("probe.k5", actual=1, expected=1)
        kinds = [r.kind for r in sink.since(0)]
        assert kinds.count("sample") == 1
        assert kinds.count("check") == 1


class TestTheSynchroniser:
    def test_a_loop_collapses_to_one_record(self, sink):
        for i in range(5000):
            _tick("probe.loop", i, i, 60.0)
        assert len(sink.since(0)) == 1

    def test_the_suppressed_ones_are_counted_not_lost(self, sink):
        """The window has to EXPIRE for the fold to be delivered.
        `reset_throttle` is not a clock -- it forgets the window and
        the pending tally with it (pinned below)."""
        for i in range(10):
            _tick("probe.count", i, i, 0.05)
        time.sleep(0.06)
        _tick("probe.count", 99, 99, 0.05)
        counts = [r.count for r in sink.since(0)]
        assert counts == [1, 10], counts

    def test_the_count_appears_in_the_message(self, sink):
        for i in range(5):
            _tick("probe.msg", i, i, 0.05)
        time.sleep(0.06)
        _tick("probe.msg", 9, 9, 0.05)
        assert "x5" in sink.since(0)[1].message()

    def test_a_failing_check_is_never_suppressed(self, sink):
        """THE LOAD-BEARING RULE. Rate-limiting failures would make the
        spam control a blindfold."""
        for i in range(500):
            _tick("probe.fails", i, -1, 3600.0)
        assert len(sink.since(0)) == 500

    def test_different_sites_are_throttled_separately(self, sink):
        """Same name from two places is two things to a reader."""
        emit("probe.site", actual=1, expected=1, every=60.0)
        emit("probe.site", actual=2, expected=2, every=60.0)
        assert len(sink.since(0)) == 2

    def test_without_every_nothing_is_throttled(self, sink):
        for i in range(50):
            emit("probe.nothrottle", actual=i, expected=i)
        assert len(sink.since(0)) == 50

    def test_reset_reopens_the_window_and_forgets_the_tally(self, sink):
        """DOCUMENTED LIMIT, pinned so it cannot become a surprise.

        `reset_throttle` is for tests and run boundaries. It clears the
        windows AND any pending tally, so observations suppressed before
        a reset are not carried into the next record. At a run boundary
        there is nowhere to carry them to; what matters is that this is
        stated rather than discovered."""
        _tick("probe.reset", 1, 1, 3600.0)
        _tick("probe.reset", 2, 2, 3600.0)
        reset_throttle()
        _tick("probe.reset", 3, 3, 3600.0)
        recs = sink.since(0)
        assert len(recs) == 2
        assert recs[1].count == 1, "pending tally is dropped by reset"


class TestTheInstanceKey:
    """Issue #57. One line, several live objects, one fold window.

    `site` is `file:line`, so two objects of one class keyed together
    and the second object's passes folded into the first object's
    record. Measured on two real `ExchangeTab` objects with three
    refresh passes each: one record, naming one exchange, `count` 1 --
    and the SAME record when the second tab's emitter was dead.

    These are the throttle-level halves of that. The widget-level drive
    lives in `tests/test_exchange_tab_emitters.py`.
    """

    def test_two_instances_on_one_line_keep_their_own_windows(
            self, sink: SignalSink) -> None:
        """THE REPAIR. Ten passes each, one window, one record each."""
        for _ in range(10):
            for eid in ("coinbase", "kraken"):
                _tick("probe.inst", 1, 1, 3600.0, instance=eid)
        got = sink.since(0)
        assert len(got) == 2
        assert [r.count for r in got] == [1, 1]

    def test_a_silent_instance_is_a_silent_record(
            self, sink: SignalSink) -> None:
        """THE FALSIFIER. One of the two stops; the record set says so.

        Before the instance existed both instances shared one window, so
        the healthy one's record was admitted and the dead one's silence
        changed nothing a reader could see. The record set now holds one
        record where two instances would have written two.
        """
        for i in range(10):
            _tick("probe.dead", 1, 1, 3600.0, instance="coinbase")
            if i == 0:
                _tick("probe.dead", 1, 1, 3600.0, instance="kraken")
        assert len(sink.since(0)) == 2

        sink2 = SignalSink(flush_every=100_000)
        set_sink(sink2)
        reset_throttle()
        for _ in range(10):
            _tick("probe.dead", 1, 1, 3600.0, instance="coinbase")
        assert len(sink2.since(0)) == 1

    def test_a_pin_that_declares_none_keys_exactly_as_before(
            self, sink: SignalSink) -> None:
        """THE UNCHANGED HALF. 5000 passes, no instance, one record."""
        for i in range(5000):
            _tick("probe.plain", i, i, 3600.0)
        assert len(sink.since(0)) == 1

    def test_the_count_belongs_to_the_instance(
            self, sink: SignalSink) -> None:
        """WHAT `count` MEANS NOW, stated by a measurement.

        The window has to expire for a fold to be delivered. Each
        instance's next admitted record carries ITS OWN suppressed
        tally: 3 folded for `coinbase`, 7 for `kraken`. Before the
        instance existed one record would have carried all ten and
        named one of the two.
        """
        for _ in range(4):
            _tick("probe.tally", 1, 1, 0.05, instance="coinbase")
        for _ in range(8):
            _tick("probe.tally", 1, 1, 0.05, instance="kraken")
        time.sleep(0.06)
        _tick("probe.tally", 1, 1, 0.05, instance="coinbase")
        _tick("probe.tally", 1, 1, 0.05, instance="kraken")
        counts = [r.count for r in sink.since(0)]
        assert counts == [1, 1, 4, 8], counts

    def test_a_failing_check_is_never_suppressed_with_an_instance(
            self, sink: SignalSink) -> None:
        """THE GUARD IS ABOVE THE THROTTLE AND THE KEY DOES NOT REACH IT.

        `emit` tests `if _judged is not False` BEFORE it calls
        `_throttle_admit`, so a red never enters a window at all --
        instanced or not.
        """
        for i in range(50):
            _tick("probe.instred", i, -1, 3600.0, instance="coinbase")
        assert len(sink.since(0)) == 50

    def test_without_every_the_instance_is_not_read(
            self, sink: SignalSink) -> None:
        """`instance` means something only beside `every`.

        Nothing outside the rate-limited branch reads it, so a pin that
        declares one without a throttle writes the same record it always
        did and leaves no window behind.
        """
        for i in range(20):
            emit("probe.noevery", actual=i, expected=i, instance="coinbase")
        assert len(sink.since(0)) == 20
        assert dict(_throttle_entries()) == {}

    def test_the_key_space_is_the_declared_ids_and_nothing_else(
            self, sink: SignalSink) -> None:
        """THE BOUND. `_THROTTLE` is never pruned, so it must not grow.

        Three ids, 300 passes: three entries. The number of entries is
        the number of DECLARED ids, not the number of passes and not the
        number of objects -- which is why the declaration is a
        configured id and never `id(self)`. Re-declaring an id reuses
        its window, so an object rebuilt under the same id adds nothing.
        """
        for _ in range(100):
            for eid in ("coinbase", "kraken", "binanceus"):
                _tick("probe.bound", 1, 1, 3600.0, instance=eid)
        entries = _throttle_entries()
        assert len(entries) == 3
        assert sorted(key[2] for key in entries) == [
            "binanceus", "coinbase", "kraken"]
        assert len(sink.since(0)) == 3


class TestTheContractStillHolds:
    def test_records_remain_frozen(self, sink):
        emit("probe.frozen2", actual=1, expected=1)
        r = sink.since(0)[0]
        with pytest.raises(Exception):
            r.name = "changed"

    def test_json_field_order_is_stable(self, sink):
        """Readability for whoever greps these after release."""
        emit("probe.order", actual=1, expected=1)
        keys = list(json.loads(sink.since(0)[0].to_json()))
        assert keys[:5] == ["ts", "seq", "module", "name", "kind"]
