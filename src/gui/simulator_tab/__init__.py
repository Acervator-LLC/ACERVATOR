"""
src/gui/simulator_tab/ — Simulator tab package.

Introduced v3.18.3 as the replacement for the retired ``nuclear_live.py``
parallel-platform engine and the deleted v3.17/v3.18 stripped-down
simulator MVP.

Design philosophy (operator directive, 2026-05-19):
  "Simulate. Verify. Implement. Observe. Calibrate. Iterate. Repeat."

The Simulator tab pairs Fleet Replay with Nuclear Mode: real
``ScrummingBot`` + ``BotManager`` + ``SmartWireManager`` + ``MRInspector``
running against a ``NuclearSimExchange`` with speed-oscillating stress and
a verification harness — the full platform exercised by simulated data.

Isolation guarantee:
  - Own ``EventBus`` instance (not the global singleton)
  - Own ``LogManager`` writing to ``logs/sim/<run_id>/``
  - Own ``BotManager`` (Phase B+)
  - No coupling to the live Trading tab's state
"""

from .simulator_tab import SimulatorTab

__all__ = ["SimulatorTab"]
