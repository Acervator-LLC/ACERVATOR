"""Calibration for the rule "A silent capture is a failed capture".

WHAT THE RULE GUARDS
====================
``src/core/logging_engine.py`` sets
``logging.getLogger("acervator").propagate = False``. ``caplog``
attaches its handler to the ROOT logger. So a record from any
``acervator.*`` logger stops at the ``acervator`` node and never
reaches ``caplog``. A test asserting on ``caplog.records`` reads an
empty list, and if its assertion is a negative one it PASSES. It fails
green. That is why nothing pushed back on it for two separate
incidents.

The guard lives in ``tests/conftest.py`` as ``_silent_capture_guard``.

WHY THIS FILE EXISTS
====================
After the migration this repository has ZERO tests that read
``caplog``, so the guard is inert against the suite. An inert guard
that nobody exercises decays into a comment. A zero is a claim about
the instrument, not about the world, so the instrument gets a positive
control: this file proves the guard still fires, and proves it stays
quiet on each shape it must not fire on.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from conftest import (  # noqa: E402
    ACERVATOR_LOG_NODE,
    _BlockedRecordProbe,
    silent_capture_verdict,
)


class TestVerdict:
    """The decision itself, isolated from pytest plumbing."""

    def test_fires_on_the_conjunction(self):
        """Fire on the conjunction.

        POSITIVE CONTROL. An empty window beside blocked traffic is the
        defect, and the guard must say so.
        """
        assert silent_capture_verdict(0, 1, marked=False) is True

    def test_silent_when_the_window_saw_something(self):
        """Stay silent: caplog got records, so it was not blind."""
        assert silent_capture_verdict(3, 5, marked=False) is False

    def test_silent_when_nothing_was_blocked(self):
        """Stay silent on an honest empty.

        No blocked traffic means nothing was logged, and a test may
        legitimately assert exactly that.
        """
        assert silent_capture_verdict(0, 0, marked=False) is False

    def test_the_marker_suppresses(self):
        """Honour the marker.

        FALSE-POSITIVE MODE 1's bound. A test watching a non-Acervator
        logger can opt out, and the opt-out must hold even on the exact
        conjunction that otherwise fires.
        """
        assert silent_capture_verdict(0, 1, marked=True) is False


class TestProbe:
    """The detector, driven with real records through the real node.

    This class is the end-to-end half of the positive control. It exercises
    the same handler the guard installs, on the same logger the live
    application configures, without asking pytest to run a nested
    session.
    """

    @staticmethod
    def _probe(handler_level: int):
        node = logging.getLogger(ACERVATOR_LOG_NODE)
        sink = logging.Handler(level=handler_level)
        probe = _BlockedRecordProbe(sink, node)
        probe.active = True
        return node, probe

    def test_counts_a_record_the_root_handler_can_never_see(self):
        """Count a record the root handler can never see.

        POSITIVE CONTROL, end to end.
        """
        node, probe = self._probe(logging.NOTSET)
        prior = node.propagate
        node.addHandler(probe)
        node.propagate = False
        try:
            logging.getLogger("acervator.calibration").error("blocked")
        finally:
            node.removeHandler(probe)
            node.propagate = prior
        assert probe.blocked == 1
        assert probe.names == {"acervator.calibration"}

    def test_ignores_a_record_that_can_still_reach_the_root(self):
        """Ignore a record that can still reach the root.

        With propagation ON the record does reach caplog, so it is not
        evidence of blindness.
        """
        node, probe = self._probe(logging.NOTSET)
        prior = node.propagate
        node.addHandler(probe)
        node.propagate = True
        try:
            logging.getLogger("acervator.calibration").error("visible")
        finally:
            node.removeHandler(probe)
            node.propagate = prior
        assert probe.blocked == 0

    def test_ignores_a_record_below_the_capture_level(self):
        """Ignore a record below the capture level.

        FALSE-POSITIVE MODE 2's real fix. A test capturing at ERROR
        while the code logs at INFO has an empty caplog for an ordinary
        reason -- the level -- not because of propagation. Counting
        that record would make the guard fire on a correct test.
        """
        node, probe = self._probe(logging.ERROR)
        prior = node.propagate
        node.addHandler(probe)
        node.propagate = False
        try:
            logging.getLogger("acervator.calibration").info("too quiet")
        finally:
            node.removeHandler(probe)
            node.propagate = prior
        assert probe.blocked == 0

    def test_ignores_records_outside_the_call_phase(self):
        """Ignore records made outside the call phase.

        Records made by other fixtures during setup or teardown are not
        the test body's, and must not be attributed to it.
        """
        node, probe = self._probe(logging.NOTSET)
        probe.active = False
        prior = node.propagate
        node.addHandler(probe)
        node.propagate = False
        try:
            logging.getLogger("acervator.calibration").error("in setup")
        finally:
            node.removeHandler(probe)
            node.propagate = prior
        assert probe.blocked == 0


class TestOrderIndependence:
    """FALSE-POSITIVE MODE 3: the guard's own order dependence.

    This is the reason the operator wanted eyes on this rule.

    A guard that SAMPLES ``propagate`` depends on whether some earlier
    test built the logging engine -- the same dependency it exists to
    catch. Measured on this tree 2026-08-24: the first file to build a
    ``LogManager`` sits at position 48 of 286 in alphabetical
    collection order, so files 1-47 run sighted, and all three caplog
    readers in the suite sat at positions 23, 33 and 35. A sampling
    guard would have been asleep for every one of them.

    The guard therefore SETS the flag instead of reading it. This test
    is the pin on that: it runs in whatever position the runner picks,
    including first, and the production condition must already hold.
    """

    def test_the_guard_establishes_the_production_condition(self, caplog):
        assert logging.getLogger(ACERVATOR_LOG_NODE).propagate is False, (
            "the guard must force the acervator node into its production "
            "state for any test that requested caplog, so the test meets "
            "the same wall in isolation that it meets in a full run"
        )
        assert caplog is not None


class TestFalsePositiveModeOne:
    """A watcher of a NON-Acervator logger.

    Unrelated Acervator logging happens in the background while this
    test watches urllib3.

    The guard cannot read intent: it sees an empty ``caplog`` beside
    blocked Acervator records and has no way to know this test never
    cared about them. The bound is the explicit marker, which carries a
    reason so it cannot be used as a silencer.
    """

    @pytest.mark.caplog_may_be_empty(
        "watches urllib3, not acervator; background acervator logging is "
        "irrelevant to the assertion"
    )
    def test_stays_green_on_a_non_acervator_watcher(self, caplog):
        with caplog.at_level(logging.DEBUG, logger="urllib3.calibration"):
            logging.getLogger("acervator.calibration").error(
                "unrelated background traffic"
            )
        assert not [
            r for r in caplog.records if r.name.startswith("urllib3")
        ], "urllib3 logged nothing, which is this test's pass condition"


class TestFalsePositiveModeTwo:
    """An intentionally-empty ``caplog`` that is the pass condition.

    Here the emptiness has an ordinary cause: the level.

    NO MARKER. This must stay green on the mechanism, not on an
    opt-out, because the level filter in the probe already tells the
    two cases apart. Compare with the pin below it: when the record IS
    at a captured level, the same shape is genuinely unfalsifiable and
    the guard is right to fire.
    """

    def test_stays_green_when_the_level_explains_the_silence(self, caplog):
        with caplog.at_level(logging.ERROR):
            logging.getLogger("acervator.calibration").info("below the capture level")
        assert (
            not caplog.records
        ), "nothing was captured, and the level is the honest reason"

    def test_the_same_shape_at_a_captured_level_is_the_defect(self):
        """Fire when the level does NOT explain the silence.

        The pin that keeps the test above from reading as a blanket
        exemption. An ERROR record under an ERROR capture level is not
        explained by the level. It is explained by propagation, and the
        verdict must fire.
        """
        node = logging.getLogger(ACERVATOR_LOG_NODE)
        sink = logging.Handler(level=logging.ERROR)
        probe = _BlockedRecordProbe(sink, node)
        probe.active = True
        prior = node.propagate
        node.addHandler(probe)
        node.propagate = False
        try:
            logging.getLogger("acervator.calibration").error("invisible")
        finally:
            node.removeHandler(probe)
            node.propagate = prior
        assert silent_capture_verdict(0, probe.blocked, marked=False) is True
