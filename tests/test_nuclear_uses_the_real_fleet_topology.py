"""Nuclear wires the REAL fleet, never an invented one.

OPERATOR, 2026-08-07: "The ONLY source beyond the user adding new bots manually
to Simulator or Paper Trader must be a fleet load that references bot_state and
all pieces / functions of the fleet must import to the Simulator or Paper
Trader." And: "no more inventing things to generate results from elements that
exist and must be tested."

WHAT WAS WRONG. `_topology_pairs` had two branches:

  1. Market Inspector proposals, when injected via `set_topologies`
  2. otherwise, a hard-coded circular wire chain — bot 1 -> bot 2 -> ... ->
     last -> bot 1 at a fixed percentage

Branch 1 never ran, because `set_topologies` had zero callers anywhere in the
codebase. So every Nuclear cycle ever executed took branch 2 and wired the
operator's fleet into a fabricated circle, silently. That circle was invented
so the tranche-chain verifier would have SOME wires to exercise, back when no
sim path built Smart Wires at all — a coverage number generated from data that
does not exist, which is the opposite of stressing the real system.

Meanwhile bot_state's top-level `smart_wires` — the fleet's actual topology —
were never loaded into Nuclear at all.

THE CORRECTED HIERARCHY, and it has no invented tier:

  1. Market Inspector proposals when injected — this is the strategy-
     propagation and swarm-topology test the mode exists for.
  2. Otherwise the fleet's PERSISTED wires from bot_state, imported with the
     fleet like every other piece of it.
  3. Neither -> wire NOTHING, and say so loudly. A run with no topology is a
     finding about the fleet, not a licence to invent one.

NOTE ON NUMBERS IN THIS FILE. Every fleet here is a TEST FIXTURE — small
synthetic configs, never the operator's data. The real fleet is 35 bots and 40
persisted wires; nothing below touches it.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.simulator_tab.nuclear_fleet_controller import (  # noqa: E402
    NuclearFleetController,
)

# --- TEST FIXTURE fleet (2 bots, 1 wire). Not the operator's 35/40. ---
FIXTURE_CONFIGS = [
    {"mode": "scrumming", "symbol": "BTC/USD", "target_balance": 100.0,
     "target_asset": "BTC", "base_currency": "USD", "_src_bot_id": "aaaa1111"},
    {"mode": "scrumming", "symbol": "ETH/USD", "target_balance": 100.0,
     "target_asset": "ETH", "base_currency": "USD", "_src_bot_id": "bbbb2222"},
]
FIXTURE_WIRES = [
    {"source_id": "aaaa1111", "target_id": "bbbb2222", "pct": 20.0},
]


class TestTheInventedTopologyIsGone:
    """Structural, read as AST — counting source text has produced a false
    reading three separate times on this project."""

    @staticmethod
    def _topology_pairs_src():
        p = REPO_ROOT / "src/gui/simulator_tab/nuclear_fleet_controller.py"
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef) and n.name == "_topology_pairs":
                return n
        pytest.fail("_topology_pairs not found")

    def test_no_modular_wraparound_remains(self):
        """The circle was `ids[(i + 1) % len(ids)]`. A modulo over the bot-id
        list is the signature of generating a topology instead of loading one.
        """
        fn = self._topology_pairs_src()
        mods = [n for n in ast.walk(fn)
                if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mod)]
        assert not mods, (
            f"a modular index remains at line(s) "
            f"{[n.lineno for n in mods]} — the fabricated circular topology "
            "is still being generated")

    def test_it_does_not_synthesize_from_a_range_over_the_ids(self):
        fn = self._topology_pairs_src()
        ranges = [n for n in ast.walk(fn)
                  if isinstance(n, ast.Call)
                  and getattr(n.func, "id", "") == "range"]
        assert not ranges, (
            "wires are still being generated positionally from the bot list "
            "rather than loaded from bot_state or a proposal")


class TestPersistedWiresImportWithTheFleet:
    @staticmethod
    def _prepared(monkeypatch, wires, configs=None):
        import src.gui.simulator_tab.fleet.bot_state_loader as loader
        monkeypatch.setattr(
            loader, "load_bot_configs_from_state",
            lambda *a, **kw: list(configs if configs is not None
                                  else FIXTURE_CONFIGS))
        monkeypatch.setattr(
            loader, "load_smart_wires_from_state", lambda *a, **kw: list(wires))
        ctl = NuclearFleetController()
        ctl._load_tablet_series = lambda syms: {
            s: [[1_700_000_000_000 + i * 300_000, 100.0, 101.0, 99.0,
                 100.0, 5.0] for i in range(8)] for s in syms}
        assert ctl.prepare() is True
        return ctl

    def test_prepare_loads_the_fleet_wires(self, monkeypatch):
        ctl = self._prepared(monkeypatch, FIXTURE_WIRES)
        assert ctl._smart_wires == FIXTURE_WIRES, (
            "bot_state's smart_wires are part of the fleet and must import "
            "with it")

    def test_they_are_handed_to_the_replay_controller(self, monkeypatch):
        """The child already knows how to import them (C20). Nuclear must
        actually pass them, or the fleet runs with its compounding engine
        switched off."""
        ctl = self._prepared(monkeypatch, FIXTURE_WIRES)
        seen = {}

        class _Spy:
            def __init__(self, **kw):
                seen.update(kw)
                self.progress = type("P", (), {
                    "finished": True, "candles_played": 0,
                    "trades_fired": 0})()
                self._bots = []

            async def start(self):
                return False

            def request_stop(self):
                pass

        import src.gui.simulator_tab.fleet.fleet_replay_controller as frc
        monkeypatch.setattr(frc, "FleetReplayController", _Spy)

        import asyncio
        asyncio.run(asyncio.wait_for(ctl._run_cycle(0), 5.0))
        assert seen.get("smart_wires") == FIXTURE_WIRES, (
            f"Nuclear built its fleet without the persisted wires; "
            f"kwargs seen: {sorted(seen)}")

    def test_an_empty_wire_set_is_announced_not_invented(self, monkeypatch):
        """A fleet that HAS bots but no wires must say so.

        (An empty bot list returns earlier and announces nothing, which is
        correct — there is no fleet to describe. The case that matters is a
        real fleet whose topology is empty.)
        """
        class _Bot:
            def __init__(self, bid):
                self.bot_id = bid
                self._smart_wire_mgr = None

        acts: list[str] = []
        ctl = self._prepared(monkeypatch, [])
        ctl._activity = acts.append
        ctl._wire_topology([_Bot("aaaa1111"), _Bot("bbbb2222")])
        joined = " ".join(acts).lower()
        assert ctl._smart_wires == []
        assert "no smart wires" in joined, (
            f"a fleet with no topology must say so rather than get one "
            f"invented for it; activity={acts}")
        assert "inert" in joined, (
            "the consequence must be stated — a reader needs to know the "
            "tranche-chain numbers will read 0 for the wire-fed links")

    def test_a_fleet_with_its_own_wires_says_it_is_using_them(self,
                                                              monkeypatch):
        """NEGATIVE CONTROL for the message above: the two cases must be
        distinguishable in the log, or 'no wires' is unfalsifiable."""
        class _Bot:
            def __init__(self, bid, mgr):
                self.bot_id = bid
                self._smart_wire_mgr = mgr

        acts: list[str] = []
        ctl = self._prepared(monkeypatch, FIXTURE_WIRES)
        ctl._activity = acts.append
        mgr = object()
        ctl._wire_topology([_Bot("aaaa1111", mgr), _Bot("bbbb2222", mgr)])
        joined = " ".join(acts).lower()
        assert "own topology" in joined and "bot_state" in joined
        assert "no smart wires" not in joined


class TestMarketInspectorInjectionTakesPrecedence:
    """The mode's actual job: receive strategy injections and stress topology
    propagation under cycling load."""

    def test_set_topologies_stores_the_proposal(self):
        ctl = NuclearFleetController()
        prop = {"id": "x", "wires": [
            {"source_asset": "BTC", "target_asset": "ETH", "pct": 15.0}]}
        ctl.set_topologies([prop])
        assert ctl._topologies == [prop]

    def test_an_injected_proposal_supplies_the_wires(self):
        ctl = NuclearFleetController()
        ctl._configs = list(FIXTURE_CONFIGS)
        ctl.set_topologies([{"id": "x", "wires": [
            {"source_asset": "BTC", "target_asset": "ETH", "pct": 15.0}]}])
        pairs = ctl._topology_pairs(["aaaa1111", "bbbb2222"])
        assert pairs == [("aaaa1111", "bbbb2222", 15.0)]

    def test_without_a_proposal_no_pairs_are_manufactured(self):
        """The whole correction in one assertion. No proposal means the
        persisted wires (already installed by the child) stand — Nuclear
        adds nothing of its own invention."""
        ctl = NuclearFleetController()
        ctl._configs = list(FIXTURE_CONFIGS)
        assert ctl._topology_pairs(["aaaa1111", "bbbb2222"]) == []
