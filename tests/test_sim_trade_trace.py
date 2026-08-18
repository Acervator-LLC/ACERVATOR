"""A sim run must record WHY a trade did not fire (C22 / SN-54).

THE DEFECT
`_emit_trade_notification` returned early for sim bots:

    # on the shared bus, which the live main_window handler
    # (main_window.py:343) forwards to the sound engine. Sim
    # runs must be silent + fast (operator scan finding #3).
    if getattr(self, "_sim_mode", False):
        return

That guard was doing real work: sim notifications reached the SHARED
bus, `main_window` forwarded them to the sound engine, and a replay
made noise. Removing it before C17 would have been a regression, not a
fix — which is why C22 is gated behind C17.

WHAT CHANGED
C17 made the sim private-bus swap FAIL CLOSED. A sim bot either holds a
private `EventBus` or is never constructed, so its notifications cannot
reach `main_window`'s handler. The guard is now redundant belt over
working braces — and it costs the operator the SENT / PLACED / FILLED /
CANCELLED trace, which is the only place a sim run records why a trade
did not fire.

THE MEASUREMENT IS AN INSTRUMENTED COUNTER, NOT SILENCE
"No sound was heard" is not evidence. A wildcard subscriber is attached
to the LIVE bus and asserted to receive exactly zero events while the
sim bot emits. Absence of sound and absence of delivery are different
claims, and only the second one is checkable.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.event_bus import EventBus, get_event_bus  # noqa: E402
from src.trading.scrumming_bot import ScrummingBot  # noqa: E402

SB = REPO_ROOT / "src" / "trading" / "scrumming_bot.py"


def _bot(sim_mode: bool, bus):
    """Minimal bot for the notification path only."""
    b = object.__new__(ScrummingBot)
    b.bot_id = "b1"
    b._sim_mode = sim_mode
    b._bus = bus
    b.config = type("C", (), {"symbol": "BTC/USD",
                              "target_asset": "BTC"})()
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
            "CANCELLED trace is lost")

    @pytest.mark.parametrize("stage", ["SENT", "PLACED", "FILLED",
                                       "CANCELLED"])
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
            "SCRUM", "CANCELLED", extra="below TA confidence floor")
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
                f"engine")
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


class TestTheGuardIsGoneAndTheReasonIsRecorded:
    def test_the_sim_early_return_is_removed(self):
        """Asserted over the AST of the function itself, not by grep —
        the comment recording the removal necessarily names the removed
        thing, and a substring search would match it forever."""
        src = SB.read_text(encoding="utf-8")
        fn = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and n.name == "_emit_trade_notification")
        for node in ast.walk(fn):
            if not isinstance(node, ast.If):
                continue
            test_src = ast.get_source_segment(src, node.test) or ""
            if "_sim_mode" not in test_src:
                continue
            body = [s for s in node.body if not isinstance(s, ast.Pass)]
            assert not (len(body) == 1
                        and isinstance(body[0], ast.Return)), (
                f"the sim early return survives at line {node.lineno}")

    def test_isolation_is_what_keeps_the_run_silent_now(self):
        """The guard was load-bearing before C17. Its replacement must
        be recorded at the site, or someone reinstates it."""
        src = SB.read_text(encoding="utf-8")
        fn = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and n.name == "_emit_trade_notification")
        seg = ast.get_source_segment(src, fn) or ""
        assert "C17" in seg or "private bus" in seg.lower(), (
            "nothing at this site explains why dropping the sim guard "
            "is safe; the next reader will put it back")
