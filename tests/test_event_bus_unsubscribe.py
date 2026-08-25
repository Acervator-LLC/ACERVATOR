"""The EventBus must be able to retract a subscription (C17 / NF-9).

THE DEFECT
`event_bus.py` returns an unsubscribe CLOSURE from `subscribe` (:120)
and has no unsubscribe METHOD. Every caller in `src/` discards the
closure, so once a handler is attached it can never be removed. That is
what makes the sim leak unfixable from outside: `BotManager.__init__`
subscribes three handlers to the process-wide bus (:1598/:1602/:1603)
before any caller can rebind `._bus`, and nothing can take them off
again.

TWO IMPLEMENTATION TRAPS, both of which produce a fix that LOOKS applied
and removes nothing:

  1. BOUND METHODS COMPARE UNEQUAL BY IDENTITY. Every handler in scope
     is `self._on_something` — a bound method. CPython builds a fresh
     bound-method object on each attribute access, so `obj.m is obj.m`
     is False while `obj.m == obj.m` is True. An `is`-based
     implementation silently matches nothing.

  2. `_subscribers` IS A `defaultdict(list)` (:84). Subscripting it on a
     miss CREATES an empty list, so a count accessor written with
     `self._subscribers[topic]` mutates the structure it is measuring
     and the before/after diff stops being deterministic.

Both are pinned below, because both would pass a naive test.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.event_bus import EventBus  # noqa: E402


class _Handler:
    """Subscribers are invoked as `callback(event)` — one positional
    argument. An earlier version of this double took only `**kw`, so
    every delivery raised TypeError inside the bus and was swallowed;
    the positive control below is what surfaced it."""

    def __init__(self):
        self.calls = 0

    def on_event(self, event=None):
        self.calls += 1


class TestTheInstrumentWorks:
    def test_a_subscribed_handler_receives(self):
        """POSITIVE CONTROL: every removal assertion below is only
        meaningful if delivery works in the first place."""
        bus, h = EventBus(), _Handler()
        bus.subscribe("t", h.on_event)
        bus.emit("t")
        assert h.calls == 1


class TestUnsubscribe:
    def test_it_exists_as_a_method(self):
        assert hasattr(EventBus, "unsubscribe")

    def test_a_removed_handler_stops_receiving(self):
        bus, h = EventBus(), _Handler()
        bus.subscribe("t", h.on_event)
        bus.unsubscribe("t", h.on_event)
        bus.emit("t")
        assert h.calls == 0

    def test_it_works_on_bound_methods(self):
        """THE trap. `h.on_event is h.on_event` is False, so an
        identity-based implementation removes nothing and the leak
        survives behind a green test."""
        h = _Handler()
        assert (
            h.on_event is not h.on_event
        ), "premise changed: bound methods now compare identical"
        assert h.on_event == h.on_event

        bus = EventBus()
        bus.subscribe("t", h.on_event)
        assert bus.unsubscribe("t", h.on_event) == 1

    def test_it_reports_how_many_it_removed(self):
        bus, h = EventBus(), _Handler()
        bus.subscribe("t", h.on_event)
        bus.subscribe("t", h.on_event)
        assert bus.unsubscribe("t", h.on_event) == 2

    def test_removing_an_absent_handler_is_zero_not_an_error(self):
        """Teardown paths call this best-effort; raising would strand
        the rest of the teardown."""
        bus, h = EventBus(), _Handler()
        assert bus.unsubscribe("t", h.on_event) == 0
        assert bus.unsubscribe("never-used", h.on_event) == 0

    def test_other_handlers_on_the_topic_survive(self):
        bus, a, b = EventBus(), _Handler(), _Handler()
        bus.subscribe("t", a.on_event)
        bus.subscribe("t", b.on_event)
        bus.unsubscribe("t", a.on_event)
        bus.emit("t")
        assert (a.calls, b.calls) == (0, 1)

    def test_the_same_handler_on_another_topic_survives(self):
        bus, h = EventBus(), _Handler()
        bus.subscribe("keep", h.on_event)
        bus.subscribe("drop", h.on_event)
        bus.unsubscribe("drop", h.on_event)
        bus.emit("keep")
        assert h.calls == 1


class TestSubscriberCount:
    def test_it_counts_a_topic(self):
        bus, h = EventBus(), _Handler()
        bus.subscribe("t", h.on_event)
        assert bus.subscriber_count("t") == 1

    def test_it_totals_across_topics_when_given_none(self):
        bus, h = EventBus(), _Handler()
        bus.subscribe("a", h.on_event)
        bus.subscribe("b", h.on_event)
        assert bus.subscriber_count() == 2

    def test_counting_an_unknown_topic_does_not_create_it(self):
        """THE second trap. `_subscribers` is a defaultdict, so a
        subscript on a miss CREATES the key — the accessor would mutate
        what it measures and the exit gate's before/after diff would
        drift on topic churn alone."""
        bus = EventBus()
        before = bus.subscriber_count()
        bus.subscriber_count("never-seen")
        assert bus.subscriber_count() == before
        assert "never-seen" not in bus.subscription_fingerprint()

    def test_unsubscribing_the_last_handler_removes_the_topic(self):
        bus, h = EventBus(), _Handler()
        bus.subscribe("t", h.on_event)
        bus.unsubscribe("t", h.on_event)
        assert "t" not in bus.subscription_fingerprint()


class TestSubscriptionFingerprint:
    def test_it_names_the_topics(self):
        """The exit gate diffs these. A bare count cannot distinguish
        '+3 leaked from BotManager' from '+1 leak, +2 legitimate', and
        the failure message would be unactionable."""
        bus, h = EventBus(), _Handler()
        bus.subscribe("wire.created", h.on_event)
        bus.subscribe("wire.created", h.on_event)
        bus.subscribe("profit.cross_bot", h.on_event)
        assert bus.subscription_fingerprint() == {
            "wire.created": 2,
            "profit.cross_bot": 1,
        }

    def test_an_empty_bus_fingerprints_empty(self):
        assert EventBus().subscription_fingerprint() == {}

    def test_it_round_trips_through_subscribe_and_unsubscribe(self):
        """The measurement the sim cycle depends on: identical before
        and after."""
        bus, h = EventBus(), _Handler()
        before = bus.subscription_fingerprint()
        bus.subscribe("t", h.on_event)
        bus.unsubscribe("t", h.on_event)
        assert bus.subscription_fingerprint() == before


class TestTheExistingClosureStillWorks:
    def test_subscribe_still_returns_a_working_closure(self):
        """NEGATIVE CONTROL. `nuclear_controller` calls the closure and
        expects None back; adding the method must not break it."""
        bus, h = EventBus(), _Handler()
        off = bus.subscribe("t", h.on_event)
        assert callable(off)
        assert off() is None
        bus.emit("t")
        assert h.calls == 0
