"""The two simulator logs are one pane, and nothing is lost in the merge.

Operator task 2026-08-08 (screenshot area 1): "Combined these two logs
and have them sit at the left where Simulator Activity Log currently
lives."

WHY AN EMITTER FIRST. Before this change neither log stream had an
emitter. `feature_telemetry` counted calls and skips but carried no
expected-vs-actual, so "both streams still arrive after the merge" was
not a checkable claim -- and one widget receiving everything looks
identical to one widget receiving a single stream twice.

`sim.06.014.event.log.line` carries the STREAM IDENTITY, which is exactly the
property a merge can destroy. These tests read that emitter rather than
inspecting widgets, so they measure what the system DID.

`FleetReplayController` calls `activity_log_cb` 22 times and
`performance_log_cb` 5 times, so both callbacks must survive the merge
as public methods regardless of how many panes exist.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.signal_contract import SignalSink, set_sink  # noqa: E402


@pytest.fixture
def sink():
    s = SignalSink(flush_every=10_000)
    set_sink(s)
    yield s
    set_sink(None)


@pytest.fixture
def tab():
    """A real SimulatorTab. Qt is required; skip rather than fail if the
    binding is unavailable so the suite still runs headless-less."""
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:                                   # pragma: no cover
        pytest.skip("PySide6 unavailable")
    QApplication.instance() or QApplication([])
    from src.gui.simulator_tab.simulator_tab import SimulatorTab
    return SimulatorTab()


class TestBothStreamsAreRecorded:
    def test_activity_line_is_emitted_with_its_stream(self, tab, sink):
        tab.log_activity("fleet loaded")
        recs = sink.records("sim.06.014.event.log.line")
        assert len(recs) == 1
        assert recs[0].actual == "activity"
        assert recs[0].context["delivered"] is True

    def test_performance_line_is_emitted_with_its_stream(self, tab, sink):
        tab.log_performance("120 candles/s")
        recs = sink.records("sim.06.014.event.log.line")
        assert len(recs) == 1
        assert recs[0].actual == "performance"

    def test_the_two_streams_stay_distinguishable(self, tab, sink):
        """THE MERGE'S FAILURE MODE. If combining the panes dropped the
        stream label, both would record identically and a lost stream
        would be invisible."""
        tab.log_activity("a1")
        tab.log_performance("p1")
        tab.log_activity("a2")
        streams = [r.actual for r in sink.records("sim.06.014.event.log.line")]
        assert streams == ["activity", "performance", "activity"]

    def test_nothing_is_dropped(self, tab, sink):
        for i in range(20):
            tab.log_activity(f"a{i}")
        for i in range(7):
            tab.log_performance(f"p{i}")
        recs = sink.records("sim.06.014.event.log.line")
        assert len(recs) == 27
        assert sum(1 for r in recs if r.actual == "activity") == 20
        assert sum(1 for r in recs if r.actual == "performance") == 7


class TestPauseIsRecordedNotSilent:
    def test_a_paused_line_still_emits_with_delivered_false(self, tab, sink):
        """A paused pane that emitted nothing would be
        indistinguishable from a stream that stopped producing."""
        tab._activity_paused = True
        tab.log_activity("suppressed")
        recs = sink.records("sim.06.014.event.log.line")
        assert len(recs) == 1
        assert recs[0].context["delivered"] is False

    def test_pause_is_per_stream(self, tab, sink):
        tab._activity_paused = True
        tab._perf_paused = False
        tab.log_activity("a")
        tab.log_performance("p")
        by = {r.actual: r.context["delivered"]
              for r in sink.records("sim.06.014.event.log.line")}
        assert by == {"activity": False, "performance": True}


class TestTheControllerContractSurvives:
    def test_both_callbacks_remain_public(self, tab):
        """`FleetReplayController` wires `activity_log_cb=log_activity`
        and `performance_log_cb=log_performance`. The merge changes
        where lines LAND, never the callback surface."""
        assert callable(tab.log_activity)
        assert callable(tab.log_performance)

    def test_both_callbacks_reach_one_widget(self, tab):
        """THE MERGE ITSELF. After combining, the two sinks must be the
        same widget -- that is what "combined" means, and it is checked
        by identity rather than by counting panes."""
        assert tab.activity_log is tab.performance_log

    def test_the_merged_widget_receives_both(self, tab):
        tab.log_activity("from-activity")
        tab.log_performance("from-performance")
        text = tab.activity_log.toPlainText()
        assert "from-activity" in text
        assert "from-performance" in text
