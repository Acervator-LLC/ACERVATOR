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

The builder asks `variant_surface` for the tab class under the screen name
`BOT_SWARM`. A build stamped for Qt gets the old widget. Every other build gets
the React tab, which holds the whole screen in one web view. React is the
running choice.

`src/gui/main_tabs/bot_swarm_tab.py` — `BotSwarmTabMixin._build_bot_swarm_tab`

```python
from ..variant_surface import BOT_SWARM, surface_class

built = surface_class(BOT_SWARM)()
```

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

In the React build the card is drawn by `bot_node.js` from the payload
`bot_node_surface` publishes. The tab page carries that module beside the wire
canvas, the quick routing matrix, the list and the theme palettes.

`src/gui/react_bot_swarm_tab.py` — `TAB_SCRIPT_ASSETS`

```python
TAB_SCRIPT_ASSETS: tuple[str, ...] = (
    "vendor/react.production.min.js",
    "vendor/react-dom.production.min.js",
    "design_tokens.js",
    "shared_widgets.js",
    "header_strip.js",
    "visualizer_themes.js",
    "bot_node.js",
    "wire_canvas.js",
    "quick_routing.js",
    "bot_swarm_list.js",
    "bot_visualizer.js",
)
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

Maturity is a growth threshold, not an age and not a share. A bot's capital is
mature once it is worth more than three times what it started with, and the
mature figure is then the whole profit above that starting capital. Below the
threshold the figure is zero, so a bot cannot fund a child on a small gain.

`src/trading/smart_wire.py` — `mature_profit_usd`

```python
MATURE_GROWTH_PCT: float = 200.0

if value < basis * (1.0 + MATURE_GROWTH_PCT / 100.0):
    return 0.0
return value - basis
```

One function decides maturity everywhere. The per-bot ledger reads it against
the seed capital, and the header strip reads it against the exchange cost basis
of each bot's holdings, so the spawn gate and the screen cannot disagree about
what mature means.

`src/trading/smart_wire.py` — `BotLedger.mature_profit_total`

```python
return mature_profit_usd(
    self.starting_balance, self.starting_balance + self.total_profit
)
```

The tab's own row label carries the threshold and reads the same constant the
maths reads, so the words on screen and the rule applied to the money move
together.

`src/gui/main_tabs/bot_swarm_tab_surface.py` — the row label

```python
MATURE_TOTAL_ROW_FORMAT = "Mature profit total (position grown past {pct}%):"

def mature_growth_pct() -> int:
    return int(round(smart_wire.MATURE_GROWTH_PCT))
```

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

## 2026-09-07 15:58 - no issue recorded - ten single-word tabs, each on its own ground

The Bot Swarm is a proprietary capital reinforcement network system that allows profit to be dynamically and strategically routed between positions with the primary intention of this being to accelerate accumulation curves. Smart Wires are dragged between active bots or the quick connection matrix can be used to route multiple streams to different destinations. Each wire can carry a different percentage amount of profit. Profit sent over Smart Wires are registered at the destination as Wire Credits and these are then distributed into standing Fold Tranches which allow them to have a Surplus that will be spent to increase the Target Balance up to the Maximum Growth Per Cycle. Yes, that is probably a mouth full but hopefully the settings and names are, for the most part, self-explanatory.

The tab is now called Swarm. It sits sixth on the bar, on the gold ground
with red text.

Each bot draws as one locust card, and the tab switches between the list and
the grid. Wires drag between nodes on the grid.

`src/gui/visualizer/bot_node.py` — `BotNodeWidget`

```python
class BotNodeWidget(QWidget):
    """Paint one bot as a locust, fed by set_bot_data and animate.

    paintEvent draws the wings, abdomen, thorax and head, then the
    symbol, the P/L and the bot_id as text.
    """
```

`SmartWireManager` in `src/trading/smart_wire.py` owns the topology and one
ledger per bot. One function bounds what a bot may export, reading the target
balance, the band edges and the ammunition the next fold needs, which stops a
bot sending away the capital it holds for its own dip.

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

At the far end, arriving USD spreads across the open fold tranches, or parks as
a pending wire credit while no tranche stands.

`src/trading/scrumming/wire_routing.py` — `apply_wire_income`

```python
def apply_wire_income(self, usd: float, source: str, ref: str = "") -> dict:
    """Apply incoming Smart Wire USD to this bot's fold queue.
```

Three functions collapse or remove a tranche and no others: merge, despawn and
clear. Despawn removes an aged record outright rather than holding it in a
delisted state, and the count lands in the discarded ledger rather than the
closed one.

`src/trading/scrumming/fold_tranches.py` — `_despawn_aged_tranches`

```python
_days = self._despawn_threshold_days()
report = {
    "threshold_days": _days,
    "fold_delisted": 0,
    "stack_delisted": 0,
    "stack_kept_live_order": 0,
    "ageless_kept": 0,
    "usd_delisted": 0.0,
}
```

The fleet, and its wires, ledgers and tranches with it, comes from one state
file alone. A restored bot connects to nothing and places no order until the
operator starts it.

`src/trading/container/restore.py` — `StateRestoreMixin.restore_bots_from_state`

```python
def restore_bots_from_state(self, state: dict) -> list[str]:
    """Recreate every persisted bot in IDLE state; return the ids restored.
```

(List View)

![](p30-i0.png)

Three sub-tabs open the screen: Bot Swarm, Simulator Swarm and Paper Swarm. The
header row holds the drag hint, an identifier privacy dot that masks the bot
hashes and the symbol labels together, the Privacy Mode button, and four
controls. Exchange filters both the swarm and the quick routing scope. Theme
lists the four palettes. View chooses List or Grid. The Wires slider sets wire
opacity from 0 to 100 %.

The table carries four named columns and eight wire lanes.

`src/gui/bot_swarm_list.py` — `COLUMN_HEADERS`

```python
COLUMN_HEADERS = ["Ticker", "Inflow", "Outflow", "% Out"] + [
    f"L{i + 1}" for i in range(LANE_COUNT)
]
```

Inflow draws green and Outflow red. % Out sums a bot's outbound wire
percentages, and a bot with no outbound wire reads 0 %. Two wires share a lane
only when their row spans do not overlap, and the dot at each end of a lane
marks the source row and the target row.

The quick routing matrix fills the right half in three zones: the source list,
the Rate field between them, and the destination list. Every checked source
wires to every checked destination at that rate, and four conditions are
refused out loud before anything is created.

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

A confirmation puts the count in front of the operator before Connect,
Disconnect or Disconnect All runs.

(Grid View)

![](p30-i1.png)

The view switch swaps the table for the node canvas. Each card carries the
symbol above, the realised profit below it, and the first eight characters of
the bot id at the foot. The profit colour is the theme's success colour at zero
and above and the error colour below, and the abdomen gradient takes that same
colour with its alpha scaled by the size of the figure.

Privacy Mode is off in the figure, so the symbol and the id both draw plain.
One field id covers all three readings on a card, the symbol, the short bot id
and the tooltip, so a card is never half masked.

`src/gui/visualizer/bot_node.py` — the symbol, drawn through the one mask

```python
p.drawText(
    QRectF(0, 2, w, 11),
    Qt.AlignCenter,
    _mask_or(symbol, "bot_swarm.identifiers"),
)
```

Theme names the palette the canvas paints in. The module declares four, and the
figure sits on Quantum Circuit. The palette decides the locust body, the
success and error colours the profit line takes, and the four corner brackets
around each card, which draw in the second accent at low alpha.

`src/gui/visualizer/themes.py` — the palette the figure is on

```python
"quantum": {
    "name": "Quantum Circuit",
    "bg": QColor(10, 15, 25),
    "accent": QColor(0, 200, 255),
    "accent2": QColor(0, 255, 200),
    "success": QColor(0, 255, 136),
    "warning": QColor(255, 180, 0),
    "error": QColor(255, 50, 80),
```

The wires cover the grid alone, because the grid is the only view whose
coordinates a wire can be drawn against. Each wire carries its own percentage,
drawn beside it. Drag between two nodes to create a wire, and right-click a
wire to remove it. The quick routing matrix on the right is the same widget the
List view shows.

A wire's percentage sits in a rounded dark badge at the midpoint of the curve,
so a wire crossing a card still reads. The Wires slider at the top right sets
the opacity of the whole overlay rather than of any one wire.

`src/gui/visualizer/wire_canvas.py` — the badge under the label

```python
label = f"{pct}%"
font = QFont("Consolas", 8, QFont.Bold)
p.setFont(font)
fm = p.fontMetrics()
tw = fm.horizontalAdvance(label) + 8
badge = QRectF(label_pt.x() - tw / 2, label_pt.y() - 9, tw, 18)
```

React draws this tab. The choice is made in one place, under the screen name
`BOT_SWARM`. A build stamped for Qt gets the old widget. Every other build gets
the web one, which holds the tab's page in a single view and answers the calls
the main window already made.

`src/gui/main_tabs/bot_swarm_tab.py` — `BotSwarmTabMixin._build_bot_swarm_tab`

```python
    def _build_bot_swarm_tab(self) -> None:
        """Build the Bot Swarm tab and add it to the main tab widget."""
        from ..variant_surface import BOT_SWARM, surface_class

        try:
            built = surface_class(BOT_SWARM)()
```

Every header control reports back to Python. The privacy dot, the Privacy Mode
button, the Exchange, Theme and View pickers and the Wires slider each send one
action. The screen then redraws from the answer.

`src/gui/react_bot_swarm_tab.py` — `BotSwarmReactTab.take`

```python
        def take(self, params: dict) -> dict:
            """Apply one action to the model, push the payload and return it."""
            answer = surface.apply_action(self._state, params)
            self._last_model = answer
            if self._page_ready:
                self._run(push_script(answer))
            return answer
```

A drag between two bots opens the rate box. A drag between two bots already
wired opens the disconnect confirmation. A drag released on empty space offers
the source bot's outgoing wires. One method decides which of the three it is,
so both screens ask the same question in the same words.

`src/gui/main_tabs/bot_visualizer_surface.py` — `BotVisualizerModel.finish_drag`

```python
    def finish_drag(self, source_id: str, target_id: str) -> Optional[dict]:
        """Set ``panel`` to what a wire drag from ``source_id`` asks for next.

        ``WireBoard.finish_drag`` decides the outcome; this turns it into
        the rate box, the disconnect confirmation or the wire picker the
        screen shows.
        """
```

The List view draws the same twelve-column table in the React tab. The tab
surface builds the list payload once, from the rows the last fleet load sent
and the wires the board holds, and hands it to the list module inside the page.

`src/gui/main_tabs/bot_visualizer_surface.py` — `swarm_list`

```python
def swarm_list(model: BotVisualizerModel) -> dict:
    """The dense list payload, from the rows ``update_bots`` last sent.

    ``bot_swarm_list_surface`` builds it, so the list draws the table and
    the lane wires the Qt ``BotListView`` and ``LaneWireCanvas`` paint.
    """
```

The list module draws the table and the see-through lane sheet over it in one
box, so a wire runs down a lane column between the two rows it joins.

`src/gui/web/bot_swarm_list.js` — `SwarmList`

```javascript
    return element(
      DIV_TAG,
      swarmProps,
      element(ListTable, { key: LIST_PART, model: model }),
      element(LaneSheet, { key: SHEET_PART, model: model })
    );
```


### The window a bot row opens

Clicking a bot opens its own settings window. Which window opens depends on the
build. The React build draws the header, the tab strip and every tab inside one
embedded browser; the Qt build draws the widget tree those tabs describe. The
Simulator opens the same window from its own bot rows.

`src/gui/main_window.py` — `_on_bot_clicked`

```python
from .variant_surface import BOT_LIVE_SETTINGS, surface_class

_cls = surface_class(BOT_LIVE_SETTINGS)
dlg = _cls(current_bot, self._bot_manager, self)
```

The React side is a subclass, not a rewrite. It replaces only the method that
builds the widgets, so an edit still travels the same route into the bot.
`_mark_changed` records the field against what the bot holds now, and
`_apply_changes` writes it. The window carries no second copy of that logic.

`src/gui/react_bot_live_settings.py` — `BotLiveSettingsReactDialog.apply_edit`

```python
field = field_for(str(asked.get("name") or ""))
if not field:
    return
self._mark_changed(field, asked.get("value"))
```

Each tab is drawn by its own renderer module into a named empty space the
window leaves for it. `TAB_PLAN` pairs the tab with that space, its module and
the surface that builds its payload from the bot. A tab whose surface refuses
the bot draws the reason in that space rather than nothing.

`src/gui/react_bot_live_settings.py` — `TAB_PLAN`, the first two rows

```python
("Status", "status-page", "acervatorLiveStatus", "live_status_tab_surface"),
(
    "Settings",
    "settings-page",
    "acervatorLiveSettingsTab",
    "live_settings_tab_surface",
),
```

Back to [the subsystem index](README.md).
