"""Fixture: zero hallucination defects. Should produce 0 findings.

Only references paths / modules that actually exist:
  - src/trading/topology_proposals.py (exists per v3.23.67)
  - src/gui/history_helpers.py (exists per v3.23.71 rebuild)
  - Imports from src.trading.topology_proposals (resolves)
"""
from __future__ import annotations

# Real paths — see src/trading/topology_proposals.py for the schema.
# Docs live at docs/audits/2026-07-31_market_inspector_topology_proposals_design.md.

from src.trading.topology_proposals import make_proposal


def use_it() -> None:
    make_proposal(
        archetype="momentum_funnel",
        assets=["BTC"], bots=[], wires=[],
        title="test", score=50.0)
