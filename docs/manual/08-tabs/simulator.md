# Simulator Tab

Reference. The second step of [the promotion pipeline](promotion-pipeline.md):
the live fleet, replayed against stored history.

## What builds it

`SimulatorTabMixin._build_simulator_tab` in
`src/gui/main_tabs/simulator_tab.py` constructs `SimulatorTab` from
`src/gui/simulator_tab/simulator_tab.py` and inserts it beside Trading.
The tab is isolated: the window's header strip hides while it is active,
and the tab draws its own `SimStatStrip` with the same ten fields against
sim balances.

Four injection points arrive from the window, each behind a `hasattr`
guard: `set_connectors_getter`, `set_bot_manager`, `set_swarm_getter` and
`set_topology_getter`. Every one is a lambda rather than a bound
instance, resolved when the operator presses Start, because the tabs are
built in an order none of them should depend on.

A mode switcher stacks two panels: Fleet Replay and Nuclear Mode.

## Fleet Replay

`FleetReplayPanel` in
`src/gui/simulator_tab/fleet/fleet_replay_panel.py` is the panel.

1. Load. `_on_load_clicked` calls `_spawn_sim_fleet`, which builds one
   real `ScrummingBot` per saved config. It uses the class body
   unchanged, which is the parity guarantee: the sim runs live's code
   against a fake exchange rather than a second implementation.
2. Configs. `load_bot_configs_from_state` and
   `load_smart_wires_from_state` in
   `src/simulator/fleet/bot_state_loader.py` read the operator's state
   file read-only and carry each bot's saved scrumming state and stats
   alongside its config. `summarize_loaded_configs` reports what loaded.
   The fleet is never fabricated; it is whatever that file holds.
3. Fetch. `_on_fetch_ytd_clicked` pulls the year's live trades so the run
   has something to be compared against, and `_compute_soft_start` picks
   the start point from `_live_trade_timestamps`.
4. Run. `FleetReplayController` in
   `src/simulator/fleet/fleet_replay_controller.py` drives it.
   `_build_sim` assembles the bots, `sim_bot_id` and `live_bot_id` keep
   the two id spaces apart, `_assert_capital_isolation` proves the sim
   holds no live capital, and `_on_sim_trade` records each fill.
   `ReplayProgress` carries candles played, trades fired and tick
   failures back to `_refresh_progress`.

`CandleSeries` in `src/simulator/fleet/candle_series.py` holds one
symbol's rows with a replay cursor and never reads past it.
`FleetSimExchange` in `src/simulator/fleet/sim_exchange.py` is the order
and balance ledger. `MasterClock` in
`src/simulator/fleet/master_clock.py` stamps every sim trade, which is
what makes a timestamp comparison against live meaningful.

`SimRunLog` in `src/trading/sim_run_log.py` persists a completed run
under the log root in the live schema.

## The candles

Stone Tablets are the history, and they are read-only throughout.
`read_tablet` and `write_tablet` in
`src/trading/stone_tablets/storage.py` move one `Tablet` between disk
and memory, and `read_manifest` carries the index. `TabletBackend` in
`src/exchange/tablet_backend.py` serves them in a ccxt shape;
`NATIVE_TIMEFRAME` names what the tablets store.

## The validation criterion

The Simulator is validated when the gates latch identically on the same
data. Not profit and loss, and not the trade count.

`GateLightsCell` in `src/gui/simulator_tab/fleet/sim_visuals.py` draws
each sim bot's scrum and fold arm state as a double-stacked LED grid, and
`_gate_cell_for` finds the row for a symbol whether the panel or the
table owns it. Both that cell and the History table's gate cell read one
vocabulary, `src/trading/gate_vocabulary.py`, so the two surfaces cannot
drift apart on what a gate is called or what blocked it.

`EmitContract(topic="bot.gate_decision")` in `src/core/emit_contracts.py`
declares the fire-time snapshot: the symbol, then the scrum and fold arm
state, the blockers behind each, and the fixture. A declared contract is
what makes a missing field visible instead of silently `None`.

`compare_trades` in `src/trading/stone_tablets/parity_harness.py` prints
a reproduction report into the Performance log, and
`format_report_lines` renders it. Read that as a report, not as the
criterion. `_note_parity_state` puts the honest label on screen: a run
with no live trades loaded is synthetic and comparable to nothing.

`SimValidationGuard` in `src/trading/sim_validation_guard.py` names the
five conditions under which a run cannot be trusted: no tablet for the
symbol, a trade before the tablet's first candle, an unresolvable
timestamp, a gate row missing required fields, and a candle address that
disagrees with the address recomputed from the tablet. The guard is
defined and covered by tests; no module under `src/` calls it.

## Nuclear Mode

`NuclearModePanel` in `src/gui/simulator_tab/nuclear_mode_panel.py`
drives `NuclearFleetController` in
`src/simulator/nuclear_fleet_controller.py`. The controller loops the
same state-file fleet over the tablet window until stopped, recording
each `NuclearCycle` so a late failure traces back to the cycle that
produced it.

`_noised_candles_for_cycle` varies the market structure per loop through
`noised_series` in `src/simulator/nuclear_candle_source.py`, writing over
no tablet. `SystemLoadOscillator` in
`src/core/system_load_oscillator.py` supplies the load pulse, capped
while its cooling regime holds, because the pulse shares a machine with
the live trading engine.

`set_swarm_hooks` connects the controller to the Bot Swarm tab's
`register_sim_run`, `update_sim_run` and `stop_sim_run`, which is how a
nuclear run appears in the Simulator Swarm sub-tab. `set_topologies`
replays a Market Inspector proposal shape across the sim bots.

Nuclear is not a validator. It runs after trade-logic alignment is
earned, its noised tape is deliberately not history, and its criteria are
coverage and survival. Nothing in it compares output to live.

`NuclearController` in `src/simulator/nuclear_controller.py` is the
earlier single-tape prototype: one scout bot walking one tape. Nothing
under `src/` constructs it. It stays because both controllers share
`nuclear_candle_source`.

## Bridge

`simulator_tab_surface` answers `simulator_tab.state`,
`fleet_replay_panel_surface` answers `fleet_replay_panel.state`,
`nuclear_mode_panel_surface` answers `nuclear_mode_panel.state`,
`sim_stat_strip_surface` answers `sim_stat_strip.state` and
`sim_visuals_surface` answers `sim_visuals.state`. The renderer modules
carry the matching names.

Back to [the subsystem index](README.md).
