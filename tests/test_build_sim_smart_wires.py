"""The sim's Smart Wire manager must route, and must not touch live (C20).

TWO FAILURES THIS FILE EXISTS TO CATCH, both of which the cascade plan
would have shipped.

1. A HARNESS THAT REPORTS WIRES AND ROUTES NOTHING.
   `import_wires` (smart_wire.py:456-478) does no existence check — it
   `setdefault`s each well-formed row and returns the count. Import 40
   wires keyed by persisted ids into a manager whose `_bot_refs` hold
   different ids and it returns 40 while every scrum takes the early
   return at scrumming_bot.py:1788. The plan's own exit criterion was
   "the replay reports 40 wires active", which that satisfies.
   So: never assert an IMPORT count. Assert money moved, and assert the
   ACTIVE count is endpoint-resolved.

2. A SIM MANAGER EMITTING ON THE OPERATOR'S LIVE BUS.
   `SmartWireManager.__init__` takes `bus=None` (smart_wire.py:217) and
   both emit paths resolve `get_event_bus()` when it is None
   (:507-511, :695-698), then emit `bot.log`. The class comment at
   :220-226 quotes the plan's "this class has no bus" and answers "That
   correction is itself wrong."
   The plan cited nuclear_fleet_controller.py:551 `SmartWireManager()`
   as the PRECEDENT TO COPY. That line is the leak — bus-less, while the
   sim bots around it are fail-closed onto private buses
   (scrumming_bot.py:393-394). The model is live's own:
   bot_container.py:1621 `SmartWireManager(bus=self._bus)`.

Note there is no single "sim bus" to borrow — each sim bot constructs its
own `EventBus()` — so the controller owns a dedicated one.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.event_bus import EventBus, get_event_bus  # noqa: E402
from src.gui.simulator_tab.fleet.fleet_replay_controller import (  # noqa: E501
    sim_bot_id,  # noqa: E402
    FleetReplayController,
)
from src.trading.smart_wire import SmartWireManager  # noqa: E402

STEP = 300_000
BASE = 1_700_000_000_000


def _candles(n=8, px=100.0):
    return [[BASE + i * STEP, px, px * 1.01, px * 0.99, px, 10.0]
            for i in range(n)]


def _cfg(symbol, src_id, target=100.0):
    return {
        "mode": "scrumming", "symbol": symbol, "target_balance": target,
        "target_asset": symbol.split("/")[0],
        "base_currency": symbol.split("/")[1],
        "_src_bot_id": src_id,
    }


def _built(configs, wires=None, acts=None):
    ctl = FleetReplayController(
        configs=configs,
        candles_by_symbol={c["symbol"]: _candles() for c in configs},
        smart_wires=wires,
        activity_log_cb=(acts.append if acts is not None else None))
    ctl._build_sim()
    return ctl


WIRE = [{"source_id": "aaaa1111", "target_id": "bbbb2222", "pct": 20.0}]
FLEET = [_cfg("BTC/USD", "aaaa1111"), _cfg("ETH/USD", "bbbb2222")]


class TestTheInstrumentWorks:
    def test_a_manager_exists_and_holds_both_bots(self):
        """POSITIVE CONTROL. Every assertion below is vacuous without a
        manager, and `_build_sim` returns early in several ways."""
        ctl = _built(FLEET, WIRE)
        assert ctl._smart_wire_mgr is not None
        assert len(ctl._bots) == 2


class TestTheWiresActuallyRoute:
    """The test that distinguishes 'wired' from 'reported wired'."""

    def test_a_source_bot_resolves_its_outgoing_wire(self):
        ctl = _built(FLEET, WIRE)
        # v3.24.82 -- both endpoints live in sim id space. Translating
        # only the bots would leave live ids in `_wires` and sim ids in
        # `_bot_refs`: disjoint keys, `get_outgoing_wires` returns {},
        # and the run logs "wires imported" while routing $0.00. That is
        # the failure this file exists to catch, so it is asserted in
        # BOTH directions.
        src = next(b for b in ctl._bots if b.config.symbol == "BTC/USD")
        assert ctl._smart_wire_mgr.get_outgoing_wires(src.bot_id) == {
            sim_bot_id("bbbb2222"): 20.0}
        assert ctl._smart_wire_mgr.get_outgoing_wires("aaaa1111") == {}

    def test_the_wire_resolves_through_the_bot_s_own_id(self):
        """The exact lookup `_route_scrum_proceeds_via_wires` performs at
        scrumming_bot.py:1787 — `get_outgoing_wires(self.bot_id)`. On the
        pre-remap baseline this returned {} because bot_id was a uuid4."""
        ctl = _built(FLEET, WIRE)
        src = next(b for b in ctl._bots if b.config.symbol == "BTC/USD")
        assert ctl._smart_wire_mgr.get_outgoing_wires(src.bot_id)

    def test_money_actually_moves_to_the_target_bot(self):
        """Not a lookup — a transfer. `distribute_fold_profit` must reach
        the target's `apply_wire_income` through `_bot_refs`."""
        ctl = _built(FLEET, WIRE)
        tgt = next(b for b in ctl._bots if b.config.symbol == "ETH/USD")
        seen = []
        tgt.apply_wire_income = lambda usd, source, **kw: seen.append(
            (usd, source))

        # v3.24.82 -- sim ids are `simulated_<live id>`, and the bot
        # itself calls `distribute_fold_profit(source_id=self.bot_id)`
        # (scrumming_bot.py:8706). So the SIM id is the production
        # lookup key; using the raw live id here would test a path no
        # bot takes. Verified: $20.00 delivered at the wire's 20%.
        src = next(b for b in ctl._bots if b.config.symbol == "BTC/USD")
        ctl._smart_wire_mgr.distribute_fold_profit(
            source_id=src.bot_id, profit_usd=100.0)

        assert seen, "no wire income reached the target bot"
        assert seen[0][0] > 0.0

    def test_a_bot_with_no_wire_routes_nothing(self):
        """NEGATIVE CONTROL — otherwise 'money moved' might just mean the
        manager pays everyone."""
        ctl = _built(FLEET, WIRE)
        assert ctl._smart_wire_mgr.get_outgoing_wires("bbbb2222") == {}


class TestTheActiveCountIsEndpointResolved:
    def test_a_wire_whose_target_is_absent_is_not_counted_active(self):
        wires = WIRE + [{"source_id": "aaaa1111",
                         "target_id": "ghost999", "pct": 10.0}]
        acts: list[str] = []
        _built(FLEET, wires, acts=acts)
        joined = " ".join(acts)
        assert "1 of 2" in joined, (
            f"expected an endpoint-resolved active count, got: {joined}")

    def test_the_import_count_alone_is_never_reported_as_active(self):
        """`import_wires` returns 2 for the fixture above. Reporting that
        is precisely the green-log-zero-effect failure."""
        wires = WIRE + [{"source_id": "ghost111",
                         "target_id": "ghost222", "pct": 10.0}]
        acts: list[str] = []
        _built(FLEET, wires, acts=acts)
        joined = " ".join(acts)
        assert "2 active" not in joined
        assert "1 of 2" in joined

    def test_a_fully_resolved_set_reports_all_of_them(self):
        acts: list[str] = []
        _built(FLEET, WIRE, acts=acts)
        assert any("1 of 1" in a for a in acts)


class TestNothingReachesTheLiveBus:
    def test_the_manager_does_not_hold_the_live_bus(self):
        ctl = _built(FLEET, WIRE)
        assert ctl._smart_wire_mgr._bus is not None, (
            "a None bus lazily resolves get_event_bus() at smart_wire.py:508")
        assert ctl._smart_wire_mgr._bus is not get_event_bus()

    @staticmethod
    def _live_spy():
        """Subscribe a recorder to the LIVE bus and return (seen, detach).

        Keeps a reference to the callback rather than passing a throwaway
        lambda to unsubscribe — `EventBus.unsubscribe(topic, callback)`
        matches on the callable, so a fresh lambda would detach nothing
        and leak the spy into every later test in the session.
        """
        live, seen = get_event_bus(), []

        def _rec(ev):
            seen.append(ev)

        unsub = live.subscribe("bot.log", _rec)

        def _detach():
            if callable(unsub):
                unsub()
            else:
                live.unsubscribe("bot.log", _rec)

        return seen, _detach

    def test_a_replay_emits_nothing_on_the_live_bus(self):
        seen, detach = self._live_spy()
        try:
            ctl = _built(FLEET, WIRE)
            ctl._smart_wire_mgr.distribute_fold_profit(
                source_id="aaaa1111", profit_usd=100.0)
        finally:
            detach()
        assert seen == [], f"sim wire activity reached the live bus: {seen}"

    def test_the_spy_is_not_dead(self):
        """PREMISE CONTROL — the assertion above is worthless unless a
        bus-less manager DOES reach this spy. Note the manager must have
        wires registered: with none, smart_wire.py:500-501 returns before
        the bus is ever resolved, so a naive version of this test passes
        for entirely the wrong reason."""
        seen, detach = self._live_spy()
        try:
            leaky = SmartWireManager()          # no bus — the :551 shape
            leaky.import_wires(WIRE)
            leaky.attach_bot("aaaa1111", object())
            leaky.distribute_fold_profit(
                source_id="aaaa1111", profit_usd=100.0)
        finally:
            detach()
        assert seen, (
            "a bus-less SmartWireManager did NOT reach the live bus — the "
            "leak test above proves nothing")


class TestTheBotRefsBelongToTheSimFleet:
    def test_set_equality_with_the_sim_fleet(self):
        ctl = _built(FLEET, WIRE)
        assert set(ctl._smart_wire_mgr._bot_refs) == {
            b.bot_id for b in ctl._bots}

    def test_every_ref_is_a_bot_this_controller_built(self):
        """Identity, not just id equality. This is what would catch a
        future implementation reaching BotManager.smart_wire_manager,
        whose _bot_refs hold the same live objects BotManager._bots does."""
        ctl = _built(FLEET, WIRE)
        mine = {id(b) for b in ctl._bots}
        assert all(id(r) in mine
                   for r in ctl._smart_wire_mgr._bot_refs.values())

    def test_the_manager_is_freshly_constructed_per_replay(self):
        a, b = _built(FLEET, WIRE), _built(FLEET, WIRE)
        assert a._smart_wire_mgr is not b._smart_wire_mgr
        assert a._smart_wire_mgr._bus is not b._smart_wire_mgr._bus


class TestSyntheticFleetsGetNoManager:
    def test_a_fleet_without_persisted_ids_has_no_wire_manager(self):
        """Wires cannot resolve against uuid4s, and a manager that holds
        wires nothing can reach is the exact green-log-zero-effect state
        this cascade removes."""
        cfgs = [_cfg("BTC/USD", "aaaa1111"), _cfg("ETH/USD", "bbbb2222")]
        for c in cfgs:
            del c["_src_bot_id"]
        ctl = _built(cfgs, WIRE)
        assert ctl._smart_wire_mgr is None

    def test_it_says_why_rather_than_going_quiet(self):
        cfgs = [_cfg("BTC/USD", "aaaa1111")]
        del cfgs[0]["_src_bot_id"]
        acts: list[str] = []
        _built(cfgs, WIRE, acts=acts)
        assert any("SYNTHETIC" in a for a in acts)


class TestTheFeatureReachesTheRealReadPath:
    """Every test above builds the controller directly. That proves the
    manager works; it does not prove the PANEL ever supplies wires, and
    a feature the production path never feeds is not shipped.

    Read as AST, never as source text — counting occurrences of a name in
    source has produced a false reading three separate times on this
    project, because comments and docstrings mentioning a symbol get
    counted as uses.
    """

    @staticmethod
    def _panel_tree():
        import ast
        p = (REPO_ROOT / "src" / "gui" / "simulator_tab" / "fleet"
             / "fleet_replay_panel.py")
        return ast.parse(p.read_text(encoding="utf-8"))

    def test_the_panel_loads_the_wires(self):
        import ast
        called = {
            getattr(n.func, "id", None) or getattr(n.func, "attr", None)
            for n in ast.walk(self._panel_tree()) if isinstance(n, ast.Call)}
        assert "load_smart_wires_from_state" in called

    def test_the_panel_passes_them_to_the_controller(self):
        import ast
        for node in ast.walk(self._panel_tree()):
            if (isinstance(node, ast.Call)
                    and getattr(node.func, "id", "") == "FleetReplayController"):
                assert any(k.arg == "smart_wires" for k in node.keywords), (
                    f"FleetReplayController built at line {node.lineno} "
                    "without smart_wires= — the manager would never be "
                    "constructed in the real app")
                return
        pytest.fail("no FleetReplayController construction found in the panel")

    def test_the_loader_reads_the_top_level_key(self, tmp_path):
        import json
        from src.gui.simulator_tab.fleet.bot_state_loader import (
            load_smart_wires_from_state)
        p = tmp_path / "bot_state.json"
        p.write_text(json.dumps({"bots": {}, "smart_wires": WIRE}),
                     encoding="utf-8")
        assert load_smart_wires_from_state(p) == WIRE

    def test_a_missing_key_is_empty_not_an_error(self, tmp_path):
        import json
        from src.gui.simulator_tab.fleet.bot_state_loader import (
            load_smart_wires_from_state)
        p = tmp_path / "bot_state.json"
        p.write_text(json.dumps({"bots": {}}), encoding="utf-8")
        assert load_smart_wires_from_state(p) == []


class TestNuclearDoesNotLeakEither:
    """`nuclear_fleet_controller.py:551` built a bus-less
    SmartWireManager, and the C20 plan cited that line as the precedent
    to copy. It is the leak. Pinned structurally so it cannot regress
    into the same shape the plan recommended.
    """

    def test_it_constructs_the_manager_with_a_bus(self):
        import ast
        p = (REPO_ROOT / "src" / "gui" / "simulator_tab"
             / "nuclear_fleet_controller.py")
        found = [n for n in ast.walk(ast.parse(p.read_text(encoding="utf-8")))
                 if isinstance(n, ast.Call)
                 and getattr(n.func, "id", "") == "SmartWireManager"]
        assert found, "no SmartWireManager construction found"
        for call in found:
            assert any(k.arg == "bus" for k in call.keywords), (
                f"SmartWireManager built without bus= at line {call.lineno}"
                " — smart_wire.py:508 then resolves the LIVE bus")


class TestLedgersAreNotImported:
    def test_wired_in_starts_at_zero(self):
        """Live's persisted ledgers carry wired_in == wired_out ==
        $1,047.49 across 48 rows, 13 of them orphans of deleted bots.
        Importing those would satisfy a 'non-zero wired_in' exit
        criterion without a single sim wire firing."""
        ctl = _built(FLEET, WIRE)
        for bot_id in (b.bot_id for b in ctl._bots):
            led = ctl._smart_wire_mgr.get_ledger(bot_id)
            if led is not None:
                assert getattr(led, "wired_in", 0.0) == pytest.approx(0.0)
                assert getattr(led, "wired_out", 0.0) == pytest.approx(0.0)
