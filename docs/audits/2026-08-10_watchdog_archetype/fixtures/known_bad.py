"""Test pins that are not wired out to the handler. TWO defects.

Ground truth: `WatchdogArchetype.review()` must produce at least one
HIGH finding here, and `main()` must exit 1. If this file ever exits 0
the archetype has gone blind and every other verdict it gives is void.

The code is deliberately CLEAN for the coding domain -- typed, no
unresolvable imports, no security findings -- so the only thing that can
fail it is the wiring. That isolation is the point: it proves the
verdict comes from the wiring and not from borrowed coding noise.

Both pins below look right in the source. Each one records into
something local, so the handler never sees a single reading and nothing
downstream can tell these pins from pins nobody wrote.

  D1  a local function named `emit` that keeps readings to itself. The
      call sites are word-for-word what a wired pin looks like, and
      `src/core/signal_contract.py` is never imported.
  D2  a helper named `_probe_emit` that appends to a list instead.
"""
from __future__ import annotations

_LOCAL: list[tuple] = []


def emit(name: str, actual: float, expected: float = 0.0) -> None:
    """D1 lives here: a private stand-in for the real `emit`."""
    _LOCAL.append((name, actual, expected))


def _probe_emit(name: str, actual: float) -> None:
    """D2 lives here: a reading that stops at a local list."""
    _LOCAL.append((name, actual, 0.0))


class Extractor:
    """A unit whose pins report into nothing."""

    def __init__(self) -> None:
        """Start with no holdings."""
        self._current_holdings = 0.0

    def contain(self, qty: float) -> None:
        """D1: reads like the real pin, reaches no handler."""
        emit("extractor.tranche_contained", actual=qty, expected=qty)

    def observe(self) -> None:
        """D2: a reading that never leaves this module."""
        _probe_emit("extractor.holdings", self._current_holdings)

    def settle(self, qty: float) -> None:
        """D1 again, on the money path where it matters most."""
        self._current_holdings = self._current_holdings + qty
        emit("tick.settled", self._current_holdings)
