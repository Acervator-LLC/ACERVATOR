"""A sim run must record WHY a trade did not fire.

`_emit_trade_notification` no longer short-circuits for sim bots. Sim
isolation is enforced by the private-bus swap failing closed: a sim bot
either holds a private ``EventBus`` or is never constructed, so its
notifications cannot reach ``main_window``'s handler and the sound
engine. Dropping the old early-return restores the SENT / PLACED /
FILLED / CANCELLED trace, the only place a sim run records why a trade
did not fire.

Silence is asserted as delivery, not as sound: a wildcard subscriber on
the LIVE bus must receive exactly zero events while a sim bot emits.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.event_bus import EventBus, get_event_bus  # noqa: E402
from src.trading.scrumming_bot import ScrummingBot  # noqa: E402


def _bot(sim_mode: bool, bus):
    """Minimal bot for the notification path only."""
    b = object.__new__(ScrummingBot)
    b.bot_id = "b1"
    b._sim_mode = sim_mode
    b._bus = bus
    b.config = type("C", (), {"symbol": "BTC/USD", "target_asset": "BTC"})()
    return b


class _Counter:
    def __init__(self):
        self.events = []

    def on_any(self, event=None):
        self.events.append(event)


class TestTheInstrumentWorks:
    def test_a_wildcard_subscriber_sees_traffic(self):
        """POSITIVE CONTROL. The whole exit gate is 'the live bus
        received ZERO events'. If a wildcard subscriber could not see
        traffic at all, that zero would mean nothing."""
        bus, c = EventBus(), _Counter()
        bus.subscribe("*", c.on_any)
        bus.emit("bot.log", bot_id="x", message="hello")
        assert len(c.events) == 1

    def test_a_live_bot_still_notifies(self):
        """NEGATIVE CONTROL: removing the sim guard must not disturb
        the live path."""
        bus, c = EventBus(), _Counter()
        bus.subscribe("*", c.on_any)
        _bot(sim_mode=False, bus=bus)._emit_trade_notification("SCRUM", "SENT")
        assert c.events, "the live notification path stopped emitting"


class TestSimRunsNowRecordTheTrace:
    def test_a_sim_bot_emits_its_notification(self):
        """SN-54: the trace is the only place a sim run records why a
        trade did not fire."""
        priv, c = EventBus(), _Counter()
        priv.subscribe("*", c.on_any)
        _bot(sim_mode=True, bus=priv)._emit_trade_notification("SCRUM", "SENT")
        assert c.events, (
            "sim bot still returns early; the SENT/PLACED/FILLED/"
            "CANCELLED trace is lost"
        )

    @pytest.mark.parametrize("stage", ["SENT", "PLACED", "FILLED", "CANCELLED"])
    def test_every_stage_is_recorded(self, stage):
        priv, c = EventBus(), _Counter()
        priv.subscribe("*", c.on_any)
        _bot(sim_mode=True, bus=priv)._emit_trade_notification("SCRUM", stage)
        assert c.events

    def test_the_cancelled_reason_survives(self):
        """The reason string is the point. A CANCELLED with no reason
        records that nothing happened without recording why."""
        priv, c = EventBus(), _Counter()
        priv.subscribe("*", c.on_any)
        _bot(sim_mode=True, bus=priv)._emit_trade_notification(
            "SCRUM", "CANCELLED", extra="below TA confidence floor"
        )
        blob = " ".join(str(getattr(e, "data", e)) for e in c.events)
        assert "below TA confidence floor" in blob


class TestTheLiveBusReceivesNothing:
    def test_zero_events_reach_the_live_bus(self):
        """THE exit-gate measurement, as an instrumented counter rather
        than 'no sound was heard'. Absence of sound and absence of
        delivery are different claims; only the second is checkable."""
        live = get_event_bus()
        c = _Counter()
        off = live.subscribe("*", c.on_any)
        try:
            priv = EventBus()
            bot = _bot(sim_mode=True, bus=priv)
            for stage in ("SENT", "PLACED", "FILLED", "CANCELLED"):
                bot._emit_trade_notification("SCRUM", stage, extra="reason")
            assert c.events == [], (
                f"{len(c.events)} sim notification(s) reached the LIVE "
                f"bus, where main_window forwards them to the sound "
                f"engine"
            )
        finally:
            off()

    def test_many_notifications_still_reach_nothing_live(self):
        """A single emit could miss by luck; a replay emits thousands."""
        live = get_event_bus()
        c = _Counter()
        off = live.subscribe("*", c.on_any)
        try:
            bot = _bot(sim_mode=True, bus=EventBus())
            for _ in range(200):
                bot._emit_trade_notification("SCRUM", "FILLED")
            assert c.events == []
        finally:
            off()
