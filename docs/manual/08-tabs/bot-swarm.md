# Bot Swarm Tab

Reference. The capital reinforcement network: the nodes, the wires
between them, and the accounting that lands routed profit.

## What builds it

`BotSwarmTabMixin._build_bot_swarm_tab` in
`src/gui/main_tabs/bot_swarm_tab.py` constructs `BotVisualizationTab`
from `src/gui/bot_visualizer.py`.

The tab holds three sub-tabs:

| Sub-tab | State |
| ------- | ----- |
| Bot Swarm | The live fleet |
| Simulator Swarm | Rows the Simulator registers while a run plays |
| Paper Swarm | Chrome only — see [paper-trader.md](paper-trader.md) |

## The nodes

Each bot draws as one `BotNodeWidget` from
`src/gui/visualizer/bot_node.py`, a locust card painted with QPainter.
`src/gui/visualizer/themes.py` supplies the palette and
`src/gui/visualizer/particle.py` the drifting motes.

`_on_view_mode_changed` switches between the list and the grid. The wire
overlay covers the grid alone, because the grid is the only view whose
coordinates a wire can be drawn against.

## Drawing a wire

Drag from one node to another. `_on_external_wire_created` also draws
wires that arrive on the `wire.created` bus topic, which is the same path
the startup restore and the topology adopt take, so one subscription
covers every source.

`QuickRoutingMatrix` in `src/gui/visualizer/quick_routing.py` is the
bulk alternative: tick source bots, tick destination bots, and
`_on_connect_clicked` creates every pair at once. `_confirm_mass` puts a
count and a description in front of the operator before a bulk connect or
disconnect runs, and `_reject` explains a refusal.

## Routing the profit

`SmartWireManager` in `src/trading/smart_wire.py` owns the topology and
one `BotLedger` per bot.

- `register_wire` and `unregister_wire` add and drop an edge, each
  carrying its own percentage.
- `distribute_fold_profit` moves that percentage of a source bot's
  realised profit to each wired target.
- `compute_safe_outflow_pct` bounds it. The function returns the
  exportable share of the scrum profit as a percentage between 0 and 100,
  reading the target balance, the band edges, the next fold's ammunition
  and the cash on hand. A bot never exports capital it needs to buy the
  dip it is waiting for.
- `export_wires`, `import_wires`, `export_ledgers` and `import_ledgers`
  carry the topology and the provenance through a save and a restart.
- `predominant_source`, `mature_profit_total` and
  `mature_profit_available` on `BotLedger` answer where a bot's capital
  came from and how much of it has aged enough to move on.

## Landing the profit

`apply_wire_income` in `src/trading/scrumming/wire_routing.py` receives
the USD at the destination. `_spread_wire_usd_over_fold_queue` distributes
it across the open fold tranches. When no tranche stands, the money parks
as `_pending_wire_credits`, and `_land_pending_wire_credits` or
`_absorb_pending_wire_credits_into` moves it into the next tranche that
opens. Parked credits are routed income, never a tranche.

Each tranche keeps its wire-credit provenance. `_add_wire_credits`
appends detail entries, `_compact_wire_credits` bounds them, and
`_roll_wire_credit_overflow` folds everything past the cap into a rolled
total that keeps the sums exact.

## The tranche book

`FoldTrancheAccountingMixin` in `src/trading/scrumming/fold_tranches.py`
owns the queued fold tranches, the discharge order the buy path reads,
and the lifetime counters. It places no orders.

`_fold_eligible_tranches` selects what may fold at the current price,
`_plan_fold_consumption` builds the plan, `_settle_fold_plan` books it,
and `_fold_discharge_order` fixes the order they discharge in.

### Merge, despawn, clear

Three functions collapse or remove a tranche. No other code path does.

**Merge.** `_top_up_remnant_fold_tranches` folds a new sell's USD into
part-spent tranches instead of opening more records, and
`_bound_new_fold_tranches` merges one sell's fresh slice back to a single
record when the fill arrived as many lots. Both reduce the record count
and move USD; neither loses any.

**Despawn.** `_despawn_aged_tranches` removes tranches older than the
bot's despawn threshold. The record goes out of `_fold_tranches`
entirely, `_fold_queue_usd` recomputes from what is left, and the count
lands in `_tranches_discarded_lifetime` rather than
`_tranches_closed_lifetime`, because a closed tranche is one that folded.
That split holds `created - closed - discarded == standing` true. An aged
stack tranche still holding a resting limit order is kept and counted
separately, since removing it would leave that order on the book with
nothing tracking it. `_despawn_threshold_days` reads the same shared
helper the settings spinbox reads, so the sweep and the control cannot
disagree about what a stored value means.

**Clear.** `clear_fold_tranches` discards every queued tranche and trades
nothing. Holdings, the main lots, the target balance and the parked wire
credits all survive it, and the report warns when parked credits remain.

## Where the fleet comes from

`bot_state.json` is the only source of the bots, and of their wires,
ledgers and tranches with them. `StateManager` in
`src/core/state_manager.py` reads and writes it;
`StateRestoreMixin.restore_bots_from_state` and
`restore_smart_wires_from_state` in `src/trading/container/restore.py`
rebuild the fleet and its topology from that one file, and
`save_all_state` writes it back. `delete_bot` is the only path that
removes a record.

## Capital claims

`CapitalRegistry` in `src/trading/capital_registry.py` holds one
`Reservation` per bot against a wallet. `request_reservation` refuses when
the claims on an exchange and base-currency pair would exceed the wallet,
`get_free` reports what is left, and `reconcile_with_exchange` settles the
claims against the venue. `src/gui/widgets/capital_registry_panel.py`
shows the table read-only.

## Bridge

`bot_visualizer_surface` answers `bot_visualizer.state`,
`bot_swarm_tab_surface` answers `bot_swarm_tab.state`,
`bot_swarm_list_surface` answers `bot_swarm_list.state`, and
`bot_node_surface`, `wire_canvas_surface`, `quick_routing_surface`,
`capital_registry_surface` and `fold_tranches_tab_surface` serve the
pieces. The renderer modules carry the matching names.

Back to [the subsystem index](README.md).
