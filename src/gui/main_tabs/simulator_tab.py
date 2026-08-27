"""Simulator tab of the main window."""

from __future__ import annotations

from typing import Any


class SimulatorTabMixin:
    """The isolated simulator surface and its injection points."""

    # Supplied by MainWindow at runtime; declared so a type checker
    # can resolve them. Annotations only: no attribute is created and
    # the runtime base stays `object`.
    _bot_manager: Any
    _main_tabs: Any
    _market_inspector: Any

    def _build_simulator_tab(self) -> None:
        """Build the Simulator tab and insert it into the main tab widget."""
        # --- Tabs 6 + 6b: Simulator and Paper Trader — REMOVED v3.16.46 ---
        # Operator directive 2026-05-10: "Delete the Simulator and
        # Paper Trader Tabs. These will be rebuilt later. We need to
        # get the critical functions fixed and clearly I have been
        # too trusting."
        #
        # Both tabs are removed from the GUI surface to focus
        # engineering attention on the live trading critical-function
        # bugs (compound mechanism, exchange-pulled position health,
        # smart wire routing, error counting, history/header data
        # integrity — see P0a-P0e in NEXT_SESSION_ORDERS.md).
        #
        # v3.18.3 — Phase A: Simulator tab skeleton lands.
        # Operator-approved 2026-05-19 design (see
        # docs/audits/2026-05-19_simulator_paper_trader_design.md).
        # Fully-isolated codebase at src/gui/simulator_tab/ + src/simulator/;
        # near-identical chrome to Trading tab; Basic Modes panel
        # launches RAIntSimBat batteries via subprocess; Nuclear
        # Mode is placeholder until Phase B lands NuclearSimExchange
        # + verification harness.
        #
        # Inserted at index 1 (immediately after Trading). When
        # Phase E adds Paper Trader at index 1, the Simulator tab
        # naturally shifts to index 2 — matches operator's
        # intended tab order:
        #   Trading | Paper Trader | Simulator | Asset Charts | ...
        from ..simulator_tab import SimulatorTab

        self._simulator = SimulatorTab()
        self._main_tabs.insertTab(1, self._simulator, "Simulator")
        # v3.23.80 — wire connectors getter for Fleet Replay's
        # Fetch YTD button. Deferred behind hasattr guard so an
        # older SimulatorTab without this hook still boots.
        if hasattr(self._simulator, "set_connectors_getter"):
            self._simulator.set_connectors_getter(
                lambda: getattr(self, "_exchange_connectors", {})
            )
        # v3.23.81 — wire bot_manager so Fetch YTD can enumerate
        # via _pairs_from_bot_manager (mirror History Tab pattern).
        # This is the authoritative path; connectors-getter above
        # is retained as a boot-safe shim only.
        if hasattr(self._simulator, "set_bot_manager"):
            self._simulator.set_bot_manager(self._bot_manager)
        # v3.24.77 — hand the Simulator Swarm to Nuclear Mode.
        #
        # Operator directive 2026-08-07: "Nuclear Mode is expected
        # to use and abuse the Simulator Bot Swarm." The row API
        # (`register_sim_run` / `update_sim_run` / `stop_sim_run`)
        # lives on BotVisualizationTab, a different top-level tab,
        # and nothing connected the two — so
        # `NuclearFleetController.set_swarm_hooks` had zero callers
        # and every swarm call inside it was a silent no-op.
        #
        # A LAMBDA, not `self._bot_viz` directly: `_bot_viz` is built
        # earlier in this method today, but binding the instance here
        # would make the wiring depend on that order never changing.
        # Resolved at Start, when both tabs certainly exist.
        if hasattr(self._simulator, "set_swarm_getter"):
            self._simulator.set_swarm_getter(lambda: getattr(self, "_bot_viz", None))
        # v3.24.79 — Market Inspector TOPOLOGY injection into Nuclear.
        #
        # Operator directive 2026-08-07: Nuclear "is supposed to be
        # able to receive strategy injections from the Market
        # Inspector to test the strategy propagation function and
        # swarm topologies under cycling load."
        #
        # READ ONLY, and NOT the adopt path wired above via
        # `set_adopt_handler`: adopting creates real bots and wires
        # on the live fleet, while this only lets the simulator read
        # a proposal's shape and replay it across sim bots.
        #
        # The Market Inspector tab is built AFTER this block, so a
        # lambda is required rather than a bound reference — it is
        # resolved when the operator presses Start.
        if hasattr(self._simulator, "set_topology_getter"):
            self._simulator.set_topology_getter(
                lambda: (
                    self._market_inspector.current_topology_proposals()
                    if hasattr(
                        getattr(self, "_market_inspector", None),
                        "current_topology_proposals",
                    )
                    else []
                )
            )
