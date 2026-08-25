"""Test pins that are all wired out to the handler. ZERO defects.

Ground truth: `WatchdogArchetype.review()` must produce zero high
findings here, and `main()` must exit 0. Any finding on this file is a
FALSE POSITIVE and must be investigated before any verdict from this
archetype is trusted anywhere else.

This file is also the FALSE-POSITIVE BRAKE CONTROL. Each brake below is
a shape the archetype must stay silent about. If a brake stops working,
this fixture starts failing, which is the only reason it is worth
shipping.

  B1  a Qt-style `.emit` carrying a human status string. Three
      mechanisms share the attribute name `.emit` in this codebase, and
      a matcher that read them all would report button text as a pin.
  B2  an EventBus `.emit` carrying a dotted topic. The bus is a
      different system. Whether a topic is declared says nothing about
      whether a pin reaches the handler.
  B3  a helper from a different instrument, called with a dotted name.
      `feature_telemetry` really is called this way in
      `fleet_replay_panel`, and it is not a pin.
  B4  an alias bound INSIDE the function that uses it. This is the
      dominant form in this codebase and every one of them is wired.
  B5  a short name that picks up the wire by plain assignment instead
      of by import. It is wired, so reporting it would accuse working
      code, and a rule that accuses working code gets switched off.
"""

from __future__ import annotations

from src.core.signal_contract import emit


class _StatusSignal:
    """Stands in for a Qt pyqtSignal. B1: `.emit` is not always a pin."""

    def emit(self, text: str) -> None:
        """Accept a human status string."""
        self._last = text


class _Bus:
    """Stands in for EventBus. B2: a bus topic is not a pin."""

    def emit(self, topic: str, **payload: object) -> None:
        """Accept a topic and a payload."""
        self._last = (topic, payload)


def _tel_call(name: str) -> None:
    """B3: a different instrument entirely. Not the pin network."""
    _seen.append(name)


_seen: list[str] = []


class Ledger:
    """A unit whose pins are all wired out to the handler."""

    def __init__(self, target: float) -> None:
        self._target_balance = target
        self._current_holdings = 0.0
        self._bus = _Bus()
        self._sig_console = _StatusSignal()

    def render(self) -> None:
        """B1: the archetype must not read 'Saved ledger' as a pin."""
        self._sig_console.emit("Saved ledger")

    def announce(self) -> None:
        """B2: a bus topic, not a pin."""
        self._bus.emit("trade.filled", bot_id="fixture", data={"n": 1})

    def refresh(self) -> None:
        """B3: a helper belonging to a different instrument."""
        _tel_call("sim.stat_strip.feed")

    def observe(self) -> None:
        """A pin wired out through the module-level import."""
        emit("pnl.event", self._current_holdings)

    def judge(self) -> None:
        """A pin that carries the expectation it was judged against."""
        emit(
            "ta.voting",
            actual=self._current_holdings,
            expected=self._target_balance,
            ok=self._current_holdings >= self._target_balance,
        )

    def contain(self, qty: float) -> None:
        """B4: an alias bound inside the function. Still wired."""
        from src.core.signal_contract import emit as _et_emit

        _et_emit("extractor.tranche_contained", actual=qty, expected=qty)

    def settle(self, qty: float) -> None:
        """B4 again, with a short alias of the kind used in the tree."""
        from src.core.signal_contract import emit as _tk

        self._current_holdings = self._current_holdings + qty
        _tk("tick.settled", actual=self._current_holdings)

    def close(self) -> None:
        """B5: the wire arrives by assignment, not by import."""
        _ta_emit("ta.closed", actual=self._current_holdings)


_ta_emit = emit  # B5: a handoff by plain assignment. Still wired.
