"""Nothing built on a sim path may latch onto the live EventBus.

C17 / SWARM-4.23, SN-42. Risk tier live-behaviour.

THE DEFECT
`BotManager.__init__` subscribes three handlers to the process-wide bus
(`bot_container.py:1598/1602/1603`) INSIDE the constructor.
`nuclear_controller.py` rebound `._bus` on the very next line after
constructing — too late. The three subscriptions were already latched,
and `EventBus` had no way to retract them (C17 adds `unsubscribe`).

The leaked handlers are bound methods of an ABANDONED SIM manager. They
stayed on the live bus for the life of the process and fired on LIVE
events, three more per replay, forever.

WHAT THIS FILE MEASURES
The exit gate: `get_event_bus()`'s subscription fingerprint is IDENTICAL
before and after building and tearing down a sim manager. The
fingerprint rather than a bare count, because "+3" cannot distinguish a
leak from legitimate growth and the failure message would be
unactionable.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.event_bus import EventBus, get_event_bus  # noqa: E402
from src.trading.bot_container import BotManager  # noqa: E402


class TestTheInstrumentWorks:
    def test_the_live_bus_is_a_singleton(self):
        """POSITIVE CONTROL. If get_event_bus() handed out a fresh bus
        each call, no leak could be observed and every assertion below
        would pass vacuously."""
        assert get_event_bus() is get_event_bus()

    def test_a_manager_really_does_subscribe(self):
        """The premise: BotManager attaches handlers at construction.
        If it stopped, the isolation assertions would be vacuous."""
        bus = EventBus()
        BotManager(bus=bus)
        assert bus.subscriber_count() >= 3, bus.subscription_fingerprint()


class TestSimConstructionDoesNotTouchTheLiveBus:
    def test_an_injected_manager_uses_the_injected_bus(self):
        bus = EventBus()
        mgr = BotManager(bus=bus)
        assert mgr._bus is bus
        assert mgr._bus is not get_event_bus()

    def test_the_live_bus_fingerprint_is_unchanged(self):
        """THE exit-gate measurement. Before C17 this grew by exactly 3
        per sim manager and never shrank."""
        live = get_event_bus()
        before = live.subscription_fingerprint()
        BotManager(bus=EventBus())
        assert live.subscription_fingerprint() == before

    def test_ten_sim_managers_leak_nothing(self):
        """A single construction could pass by luck; accumulation is
        what the operator actually suffered."""
        live = get_event_bus()
        before = live.subscription_fingerprint()
        for _ in range(10):
            BotManager(bus=EventBus())
        assert live.subscription_fingerprint() == before

    def test_the_handlers_land_on_the_private_bus(self):
        """Not merely absent from the live bus — present on the right
        one. A manager that subscribed to nothing would pass the test
        above while being broken."""
        bus = EventBus()
        BotManager(bus=bus)
        fp = bus.subscription_fingerprint()
        assert fp.get("profit.cross_bot") == 1
        assert fp.get("wire.created") == 1
        assert fp.get("wire.removed") == 1


class TestSubscriptionsCanBeRetracted:
    def test_detach_removes_them_all(self):
        bus = EventBus()
        mgr = BotManager(bus=bus)
        n = mgr.detach_bus()
        assert n == 3
        assert bus.subscription_fingerprint() == {}

    def test_detach_is_idempotent(self):
        """Teardown can run twice; the second must not double-remove or
        raise."""
        bus = EventBus()
        mgr = BotManager(bus=bus)
        mgr.detach_bus()
        assert mgr.detach_bus() == 0

    def test_a_full_build_and_teardown_round_trips(self):
        """Build on the LIVE bus deliberately — the live path is
        unchanged by C17 — then prove it can be undone."""
        live = get_event_bus()
        before = live.subscription_fingerprint()
        mgr = BotManager()
        assert (
            live.subscription_fingerprint() != before
        ), "a default-constructed manager should attach to the live bus"
        mgr.detach_bus()
        assert live.subscription_fingerprint() == before


class TestTheDefaultIsUnchangedForLive:
    def test_no_bus_argument_still_uses_the_process_wide_bus(self):
        """NEGATIVE CONTROL. C17 must not alter live construction — the
        rollback note depends on this."""
        mgr = BotManager()
        try:
            assert mgr._bus is get_event_bus()
        finally:
            mgr.detach_bus()


class TestTheNuclearControllerInjects:
    def test_it_passes_the_bus_at_construction(self):
        """Structural: rebinding `._bus` after the fact is the defect,
        so the fix must be visible as an argument at the call site."""
        import ast

        nc = REPO_ROOT / "src" / "gui" / "simulator_tab" / "nuclear_controller.py"
        tree = ast.parse(nc.read_text(encoding="utf-8"))
        calls = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "BotManager"
        ]
        assert calls, "BotManager is no longer constructed here"
        for c in calls:
            kw = {k.arg for k in c.keywords if k.arg}
            assert "bus" in kw, (
                f"BotManager at line {c.lineno} is constructed without an "
                f"injected bus; rebinding ._bus afterwards is too late"
            )

    def test_teardown_detaches(self):
        import ast

        nc = REPO_ROOT / "src" / "gui" / "simulator_tab" / "nuclear_controller.py"
        tree = ast.parse(nc.read_text(encoding="utf-8"))
        calls = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "detach_bus"
        ]
        assert calls, "nuclear teardown never retracts the subscriptions"
