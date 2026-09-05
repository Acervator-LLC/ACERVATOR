# Bot Swarm Tab

Reference. The capital reinforcement network: the nodes, the wires
between them, and the accounting that lands routed profit.

## What builds it

`BotSwarmTabMixin._build_bot_swarm_tab` in
`src/gui/main_tabs/bot_swarm_tab.py` constructs the visualizer and adds it to
the tab row. The tab holds three sub-tabs.

| Sub-tab | State |
| ------- | ----- |
| Bot Swarm | The live fleet |
| Simulator Swarm | Rows the Simulator registers while a run plays |
| Paper Swarm | Chrome only — see [paper-trader.md](paper-trader.md) |

## The nodes

Each bot draws as one locust card, painted with QPainter. A theme module
supplies the palette and a particle module the drifting motes.

`src/gui/visualizer/bot_node.py` — `BotNodeWidget`

```python
class BotNodeWidget(QWidget):
    """Paint one bot as a locust, fed by set_bot_data and animate.

    paintEvent draws the wings, abdomen, thorax and head, then the
    symbol, the P/L and the bot_id as text.
    """
```

One handler switches between the list and the grid. The wire overlay covers the
grid alone, because the grid is the only view whose coordinates a wire can be
drawn against.

## Drawing a wire

Drag from one node to another. Wires that arrive on the bus draw through the
same handler, which is the path the startup restore and the topology adopt both
take, so one subscription covers every source.

`src/gui/bot_visualizer.py` — `_on_external_wire_created`

```python
def _on_external_wire_created(self, event) -> None:
    """Add the ``wire.created`` event's wire to ``_wires`` when new.

    A repeated pair updates its pct and adds no second entry.
    """
```

The quick routing matrix is the bulk alternative: tick source bots, tick
destination bots, and every pair lands at once. Before that runs, the handler
refuses four things and says which.

`src/gui/visualizer/quick_routing.py` — `QuickRoutingMatrix._on_connect_clicked`

```python
if not (0.0 <= pct <= 100.0):
    self._reject(f"Rate {pct} is outside 0–100%.")
    return
if not sources:
    self._reject("No SOURCE bots are checked.")
    return
if not dests:
    self._reject("No DESTINATION bots are checked.")
    return
if pct <= 0:
    self._reject(
        "Rate is 0% — that would create wires that route " "nothing."
    )
    return
```

`_confirm_mass` puts a count and a description in front of the operator before
a bulk connect or disconnect runs.

## Routing the profit

`SmartWireManager` in `src/trading/smart_wire.py` owns the topology and one
ledger per bot.

| Method | What it does |
| ------ | ------------ |
| `register_wire` | Adds an edge carrying its own percentage |
| `unregister_wire` | Drops one edge |
| `distribute_fold_profit` | Moves that percentage of realised profit to each wired target |
| `export_wires`, `import_wires` | Carry the topology through a save and a restart |
| `export_ledgers`, `import_ledgers` | Carry the provenance through the same |

Three readings on the per-bot ledger answer where a bot's capital came from and
how much of it has aged enough to move on.

| Reading on `BotLedger` | Answers |
| ---------------------- | ------- |
| `predominant_source` | Which bot sent the most of what this one holds |
| `mature_profit_total` | Wire profit past its maturity age |
| `mature_profit_available` | How much of that is free to move now |

One function bounds what a bot may send away. It reads the target balance, the
band edges, the ammunition the next fold needs and the cash on hand, and returns
the exportable share as a percentage. A bot never exports the capital it is
holding to buy the dip it is waiting for.

`src/trading/smart_wire.py` — `compute_safe_outflow_pct`

```python
def compute_safe_outflow_pct(
    scrum_profit_usd: float,
    target_balance_usd: float,
    current_price: float,
    band_lower: float,
    band_upper: float,
    next_fold_ammo_usd: float,
    current_cash_usd: float,
    compound_growth_pct: float,
    retained_this_cycle_usd: float,
) -> float:
```

## Landing the profit

The USD arrives at the destination and spreads evenly across the open fold
tranches. Where no tranche stands, it parks instead, and the parked pool drains
into the next tranche that opens. Parked credits are routed income, never a
tranche.

`src/trading/scrumming/wire_routing.py` — `apply_wire_income`

```python
def apply_wire_income(self, usd: float, source: str, ref: str = "") -> dict:
    """Apply incoming Smart Wire USD to this bot's fold queue.
```

Each tranche keeps its wire-credit provenance, held by three methods.

| Method | What it does |
| ------ | ------------ |
| `_add_wire_credits` | Appends one detail entry per arrival |
| `_compact_wire_credits` | Bounds how many entries a tranche holds |
| `_roll_wire_credit_overflow` | Folds everything past the cap into a rolled total that keeps the sums exact |

## The tranche book

`FoldTrancheAccountingMixin` in `src/trading/scrumming/fold_tranches.py` owns
the queued fold tranches, the discharge order the buy path reads, and the
lifetime counters. It places no orders.

Four methods carry the fold through, in this order.

| Method | Step |
| ------ | ---- |
| `_fold_eligible_tranches` | Selects what may fold at the current price |
| `_fold_discharge_order` | Fixes the order they discharge in |
| `_plan_fold_consumption` | Builds the plan |
| `_settle_fold_plan` | Books it |

### Merge, despawn, clear

Three functions collapse or remove a tranche. No other code path does.

**Merge.** `_top_up_remnant_fold_tranches` folds a new sell's USD into
part-spent tranches instead of opening more records, and
`_bound_new_fold_tranches` merges one sell's fresh slice back to a single
record when the fill arrived as many lots. Both reduce the record count and
move USD; neither loses any.

**Despawn.** Aged tranches are removed outright. The record leaves the book,
the queue total recomputes from what is left, and the count lands in the
discarded ledger rather than the closed one, because a closed tranche is one
that folded. That split holds one invariant true.

`src/trading/scrumming/fold_tranches.py` — `_despawn_aged_tranches`

```python
def _despawn_aged_tranches(self, now: Optional[float] = None) -> dict:
    """Remove tranches older than ``config.tranche_despawn_days``.

    Removing a fold tranche recomputes ``_fold_queue_usd``, the
    derived aggregate behind the tick's ``_fold_queue_usd == 0``
    short-circuit and the panel's "Parked USD", and counts the
    record in ``_tranches_discarded_lifetime``, never in
    ``_tranches_closed_lifetime``, because a closed tranche is one
    that FOLDED. That split keeps
    ``created - closed - discarded == standing`` true.
```

An aged stack tranche still holding a resting limit order is kept and counted
separately, since removing it would leave that order on the book with nothing
tracking it. The threshold reads the same shared helper the settings spinbox
reads, so the sweep and the control cannot disagree about what a stored value
means.

**Clear.** `clear_fold_tranches` discards every queued tranche and trades
nothing. Holdings, the main lots, the target balance and the parked wire
credits all survive it, and the report warns when parked credits remain.

## Where the fleet comes from

One file is the only source of the bots, and of their wires, ledgers and
tranches with them. `StateManager` in `src/core/state_manager.py` reads and
writes it. Two restore methods rebuild the fleet and its topology from it, and
one save method writes it back. A restored bot connects to nothing and places
no order until the operator starts it.

`src/trading/container/restore.py` — `StateRestoreMixin.restore_bots_from_state`

```python
def restore_bots_from_state(self, state: dict) -> list[str]:
    """Recreate every persisted bot in IDLE state; return the ids restored.

    Connects to no exchange and places no order. Each restored bot carries
    a ``_restored`` flag and stays IDLE until the operator starts it, which
    is what triggers the exchange sync before any trading.
    """
```

`restore_smart_wires_from_state` in the same mixin rebuilds the topology.
`delete_bot` is the only path that removes a record.

## The list view

The table carries four named columns and eight wire lanes.

`src/gui/bot_swarm_list.py` — `COLUMN_HEADERS`

```python
COLUMN_HEADERS = ["Ticker", "Inflow", "Outflow", "% Out"] + [
    f"L{i + 1}" for i in range(LANE_COUNT)
]
```

Two wires share a lane only when their row spans do not overlap, and the
allocator takes the first free lane in order.

`src/gui/bot_swarm_list.py` — `BotSwarmLaneAllocator.assign`

```python
def assign(self, wires: list[tuple[str, int, int]]) -> dict[str, Optional[int]]:
    """Place every ``(wire_id, row_a, row_b)`` triple in ``wires``.
```

## Capital claims

One reservation per bot stands against a wallet. A total above the wallet
figure is refused whole, and the free figure reports what is left. The claims
settle against the venue, because the exchange is the authority.

`src/trading/capital_registry.py` — `CapitalRegistry.request_reservation`

```python
"""Create or replace ``bot_id``'s ``Reservation`` and return
``(granted, reason, granted_usd)``.

A total above the ``_wallet_usd`` figure is refused whole with
``granted_usd`` 0, and a ``_wallet_usd`` of None grants unchecked.
"""
```

The reservation table reaches the frontend through its own bridge method, named
in the table at the foot of this file. The Qt panel beside it,
`CapitalRegistryPanel`, is declared and no screen builds it.

## Bridge

Eight methods serve this screen, and the renderer modules carry the matching
names.

| Bridge method | Serves |
| ------------- | ------ |
| `bot_visualizer.state` | The whole tab |
| `bot_swarm_tab.state` | The three sub-tabs and the header row |
| `bot_swarm_list.state` | The list view and its lanes |
| `bot_node.state` | One locust card |
| `wire_canvas.state` | The wire overlay on the grid |
| `quick_routing.state` | The quick routing matrix |
| `capital_registry.rows` | The reservation table |
| `fold_tranches_tab.state` | The tranche book |

Back to [the subsystem index](README.md).
