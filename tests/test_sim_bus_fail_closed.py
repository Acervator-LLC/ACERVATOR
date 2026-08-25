"""A sim path that cannot isolate its bus must abort (C17 / SN-39).

THE DEFECT
`ScrummingBot.__init__`'s sim private-bus swap was:

    try:
        self._bus = EventBus()
    except Exception as _bus_exc:
        logger.warning("sim_mode: failed to isolate event bus (%s) — "
                       "sim emits may reach live logs", _bus_exc)

It logged and CONTINUED, leaving `self._bus` pointing at the
process-wide bus. The warning said so out loud: "sim emits may reach
live logs". One failed construction silently reinstated the exact
condition this cascade exists to prevent.

Method rule M10: a sim path that cannot obtain its private bus aborts
with an operator-visible reason. Losing a sim run is cheap.

ALSO PINNED HERE — the surface the cascade plan says does not exist.
The plan's own scope correction reads: "SmartWireManager takes no bus
and emits nothing, so SN-28's stated fix is misdiagnosed." It resolves
`get_event_bus()` at smart_wire.py:491 and :675 and emits `bot.log` on
both paths, and `BotManager` constructs one. Verified against source
2026-08-07 before this file was written.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.event_bus import EventBus, get_event_bus  # noqa: E402
from src.trading.phantom_balance import TimeframeCoordinator  # noqa: E402
from src.trading.smart_wire import SmartWireManager  # noqa: E402

SB = REPO_ROOT / "src" / "trading" / "scrumming_bot.py"


class TestTheSimSwapFailsClosed:
    def test_the_swap_raises_rather_than_warning(self):
        """Structural, over the AST: the handler around the private-bus
        construction must raise, not fall through."""
        src = SB.read_text(encoding="utf-8")
        fn = next(
            n
            for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.FunctionDef) and n.name == "__init__"
        )
        target = None
        for node in ast.walk(fn):
            if not isinstance(node, ast.Try):
                continue
            seg = ast.get_source_segment(src, node) or ""
            if "EventBus()" in seg:
                target = node
                break
        assert target is not None, "the sim private-bus swap is gone"
        for handler in target.handlers:
            raises = [n for n in ast.walk(handler) if isinstance(n, ast.Raise)]
            assert raises, (
                "the sim bus-isolation handler still swallows the "
                "failure; self._bus would stay on the live bus"
            )

    def test_the_old_warning_text_is_gone(self):
        """That string named the defect out loud: 'sim emits may reach
        live logs'. Its presence would mean the swallow survived."""
        src = SB.read_text(encoding="utf-8")
        fn = next(
            n
            for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.FunctionDef) and n.name == "__init__"
        )
        seg = ast.get_source_segment(src, fn) or ""
        idx = seg.find("sim emits may reach live logs")
        if idx >= 0:
            # Allowed only inside the explanatory comment, never as a
            # live logger call.
            line_start = seg.rfind("\n", 0, idx) + 1
            assert (
                seg[line_start:idx].lstrip().startswith("#")
            ), "the log-and-continue warning is still live code"

    def test_the_abort_names_the_reason(self):
        src = SB.read_text(encoding="utf-8")
        fn = next(
            n
            for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.FunctionDef) and n.name == "__init__"
        )
        seg = ast.get_source_segment(src, fn) or ""
        assert "sim bus isolation failed" in seg


class TestTheCoordinatorInheritsTheBus:
    def test_it_accepts_an_injected_bus(self):
        bus = EventBus()
        assert TimeframeCoordinator(bus=bus)._bus is bus

    def test_it_defaults_to_the_live_bus(self):
        """NEGATIVE CONTROL: live construction unchanged."""
        assert TimeframeCoordinator()._bus is get_event_bus()

    def test_scrumming_bot_threads_its_own_bus_in(self):
        """The coordinator is constructed AFTER the private-bus swap and
        previously without the bus, so a sim bot's coordinator emitted
        on the live bus while the bot itself was isolated."""
        src = SB.read_text(encoding="utf-8")
        calls = [
            n
            for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.Call)
            and getattr(n.func, "id", "") == "TimeframeCoordinator"
        ]
        assert calls, "TimeframeCoordinator is no longer constructed here"
        for c in calls:
            assert "bus" in {k.arg for k in c.keywords if k.arg}, (
                f"TimeframeCoordinator at line {c.lineno} does not "
                f"receive the bot's bus"
            )


class TestSmartWireManagerIsInjectable:
    """The plan says this class 'takes no bus and emits nothing'. It
    resolves get_event_bus() at :491 and :675 and emits on both."""

    def test_it_accepts_an_injected_bus(self):
        bus = EventBus()
        assert SmartWireManager(bus=bus)._bus is bus

    def test_bot_manager_passes_its_bus_down(self):
        from src.trading.bot_container import BotManager

        bus = EventBus()
        mgr = BotManager(bus=bus)
        try:
            assert mgr._smart_wire_mgr._bus is bus, (
                "the wire manager resolves the live bus even though its "
                "owner is isolated"
            )
        finally:
            mgr.detach_bus()

    def test_no_emit_site_resolves_the_global_bus_unconditionally(self):
        """Structural sweep: every get_event_bus() in this module must
        sit behind an injected-bus check, or a future emit site
        reintroduces the leak by forgetting."""
        import src.trading.smart_wire as m

        src = Path(m.__file__).read_text(encoding="utf-8")
        lines = src.splitlines()
        for i, line in enumerate(lines):
            if "get_event_bus" not in line or "import" not in line:
                continue
            window = "\n".join(lines[max(0, i - 6) : i])
            assert "_bus" in window, (
                f"get_event_bus at line {i + 1} is reached without "
                f"consulting an injected bus first"
            )
