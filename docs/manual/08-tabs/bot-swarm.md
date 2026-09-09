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
canvas, the quick routing matrix and the theme palettes.

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
    "bot_visualizer.js",
)
```

The grid of locust cards is the whole screen. The wire overlay covers it,
because the grid is the only surface whose coordinates a wire can be drawn
against.

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

Seven methods serve this screen, and the renderer modules carry the matching
names.

| Bridge method | Serves |
| ------------- | ------ |
| `bot_visualizer.state` | The whole tab |
| `bot_swarm_tab.state` | The three sub-tabs and the header row |
| `bot_node.state` | One locust card |
| `wire_canvas.state` | The wire overlay on the grid |
| `quick_routing.state` | The quick routing matrix |
| `capital_registry.rows` | The reservation table |
| `fold_tranches_tab.state` | The tranche book |

## 2026-09-07 15:58 - no issue recorded - ten single-word tabs, each on its own ground

The Bot Swarm is a proprietary capital reinforcement network system that allows profit to be dynamically and strategically routed between positions with the primary intention of this being to accelerate accumulation curves. Smart Wires are dragged between active bots or the quick connection matrix can be used to route multiple streams to different destinations. Each wire can carry a different percentage amount of profit. Profit sent over Smart Wires are registered at the destination as Wire Credits and these are then distributed into standing Fold Tranches which allow them to have a Surplus that will be spent to increase the Target Balance up to the Maximum Growth Per Cycle. Yes, that is probably a mouth full but hopefully the settings and names are, for the most part, self-explanatory.

The tab is now called Swarm. It sits sixth on the bar, on the gold ground
with red text.

Each bot draws as one locust card on the grid, and wires drag between nodes.

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

Three sub-tabs open the screen: Bot Swarm, Simulator Swarm and Paper Swarm. The
header row holds the drag hint, an identifier privacy dot that masks the bot
hashes and the symbol labels together, the Privacy Mode button, and three
controls. Exchange filters both the swarm and the quick routing scope. Theme
lists the four palettes. The Wires slider sets wire opacity from 0 to 100 %.

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

Each card carries the symbol above, the realised profit below it, and the
first eight characters of the bot id at the foot. The profit colour is the
theme's success colour at zero and above and the error colour below, and the
abdomen gradient takes that same colour with its alpha scaled by the size of
the figure.

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

The wires cover the grid, because the grid is the only surface whose
coordinates a wire can be drawn against. Each wire carries its own percentage,
drawn beside it. Drag between two nodes to create a wire, and right-click a
wire to remove it.

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
button, the Exchange and Theme pickers and the Wires slider each send one
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

## 2026-09-09 22:12 - #128 - one view, growth stages, and wires that hang

List View is gone. The header row now holds the drag hint, the identifier
privacy dot, the Privacy Mode button, Exchange, Theme and the Wires slider. The
View picker between Theme and Wires is removed, and the grid of locust cards is
the whole left pane.

`src/gui/bot_visualizer.py` — the grid goes straight into the row

```python
            inner_hbox = QHBoxLayout()
            # No gap: _quick_routing_matrix takes every pixel the grid leaves.
            inner_hbox.setSpacing(0)
            inner_hbox.addWidget(self._grid_widget)
            inner_hbox.addWidget(self._quick_routing_matrix, stretch=1)
```

### The card is smaller and the grid is wider

A card asks for 88 by 78 pixels, down from 112 by 98. That is 6,864 pixels of
area against 10,976, a drop of 37 per cent, and the grid fits eight columns
where it fitted six. The three text rows are measured in points rather than in
card units, so they survive the smaller card unchanged; the insect body scales
by the same ratio as the card.

`src/gui/visualizer/bot_node.py` — the card size

```python
CARD_WIDTH_PX = 88
CARD_HEIGHT_PX = 78
```

### Four growth stages, keyed on realised profit

Each card sits in one of four stages. The stage comes from the bot's realised
profit measured against its cost basis, both pulled from the exchange, and the
200 per cent floor is the same number the Smart Wire maturity test reads.

| Stage | Realised growth | Dominant colour | Decoration |
| ----- | --------------- | --------------- | ---------- |
| Hopper | 0 to 99 % | grey and black | wing buds, two tergites |
| Fledgling | 100 to 199 % | red and white | three tergites |
| Immature adult | 200 to 299 % | silver | full grown, four tergites |
| Mature adult | 300 % and over | gold | three crown spines |

The stage names are the published ones. They come from the FAO Desert Locust
Guidelines, part one, Biology and behaviour, by Symmons and Cressman, which names
the hopper, the fledgling, the immature adult and the mature adult in that order.
The module records that source beside the names.

`src/gui/visualizer/growth_stage.py` — the source and the floors

```python
STAGE_SOURCE = (
    "FAO Desert Locust Guidelines 1. Biology and behaviour, Symmons and Cressman"
)

HOPPER_FLOOR_PCT = 0.0
FLEDGLING_FLOOR_PCT = 100.0
IMMATURE_FLOOR_PCT = MATURE_GROWTH_PCT
MATURE_FLOOR_PCT = 300.0
```

One function turns the two exchange figures into the percentage. It returns
nothing at all when the basis is absent or not above zero, which is how a bot the
venue has not answered for is kept out of a stage it has not earned.

`src/gui/visualizer/growth_stage.py` — `realised_growth_pct`

```python
    if not math.isfinite(basis) or not math.isfinite(profit) or basis <= 0.0:
        return None
    return profit / basis * PCT_SCALE
```

A second function reads the stats dict the fleet load carries and refuses a bot
whose exchange reading is stale. A card with no reading draws as a Hopper and
prints an em dash where the percentage goes, never a zero.

`src/gui/visualizer/growth_stage.py` — `growth_pct_from_stats`

```python
    if fresh <= 0.0:
        return None
    return realised_growth_pct(stats.get(BASIS_KEY), stats.get(REALISED_KEY))
```

The two figures reach the screen through the bot status snapshot, which now
carries them beside the year-to-date sums.

`src/trading/bot_container.py` — `get_status`, the three added stats

```python
                "realized_pnl_exchange": round(
                    float(getattr(self.stats, "realized_pnl_exchange", 0.0) or 0.0), 4
                ),
                "cost_basis_total_exchange": round(
                    float(getattr(self.stats, "cost_basis_total_exchange", 0.0) or 0.0),
                    4,
                ),
                "exchange_data_fresh_ts": float(
                    getattr(self.stats, "exchange_data_fresh_ts", 0.0) or 0.0
                ),
```

### Every stage colour is a theme token

No card holds a colour of its own. Each theme carries a body tone and a trim tone
for each stage, and the trim is also the colour the growth figure is printed in.
The bot id line reads its colour from the same place.

`src/gui/theme_engine.py` — the stage tokens on `ThemeTokens`

```python
    locust_hopper_body: str = "#4a4a52"
    locust_hopper_trim: str = "#9a9aa6"
    locust_fledgling_body: str = "#c4303f"
    locust_fledgling_trim: str = "#f2f2f7"
    locust_immature_body: str = "#9ea4ad"
    locust_immature_trim: str = "#e2e6ec"
    locust_mature_body: str = "#b8912c"
    locust_mature_trim: str = "#f0c64a"
    locust_id_text: str = "#8c8ca8"
```

Every text colour on a card was measured against every canvas ground. One
hundred and sixty readings were taken, five app themes by four canvas palettes by
eight text roles, and all one hundred and sixty clear the WCAG AA floor of
4.5 to 1. On the Quantum Circuit ground the symbol reads 13.35 to 1, the positive
P/L 14.30 to 1, the negative P/L 5.32 to 1 and the bot id 5.87 to 1. The four
growth figures read 6.89, 17.18, 15.31 and 11.76 to 1.

`src/design_system.py` — the measure used

```python
def validate_contrast(fg: str, bg: str, large_text: bool = False) -> tuple[bool, float]:
```

### What the card says without a hover

Four readings, in the order they are drawn. The symbol names the market. The P/L
is the realised figure in dollars. The growth figure beneath it is the percentage
that placed the card in its stage. The short bot id at the foot separates two
bots on one market. A one-letter stage badge sits in the top right corner.

`src/gui/visualizer/bot_node.py` — the growth figure and the badge

```python
            p.drawText(
                QRectF(0, h - 31, w, 9),
                Qt.AlignCenter,
                growth_text(growth_pct),
            )
```

The tooltip carries the stage in words and the same percentage, so the colour on
the card is never the only place the stage is stated.

### The animation repaints eight times less often

Every coroutine in this application runs on the window's own thread, so a card
that repaints on every frame of the 33 millisecond timer spends that thread. A
still card now repaints every fourth frame. Measured over 300 frames, both builds
repaint a still card 75 times, which is 7.58 times a second. A card holding a
trade ring or a speck still repaints on every frame until they fade. Across a
fleet of 38 cards that is 288 repaints a second where it was 1,152.

`src/gui/visualizer/bot_node.py` — `animate`

```python
            self._since_repaint += dt
            busy = bool(self._trade_pulses or self._particles)
            if not busy and self._since_repaint < REPAINT_INTERVAL_S:
                return False
            self._since_repaint = 0.0
            self.update()
            return True
```

### A wire hangs as a catenary

A wire is no longer a curve bent through a midpoint. It is the curve a cable
makes when it hangs between two points, which has a published equation. The wire
carries 18 per cent more cable than the straight distance between the two bots,
and the two wires of a bidirectional pair hang at different depths.

`src/gui/main_tabs/wire_canvas_surface.py` — `catenary_parameter`

```python
    wanted_ratio = math.sqrt(length * length - drop * drop) / span
    ceiling_ratio = math.sinh(CATENARY_U_MAX) / CATENARY_U_MAX
    if wanted_ratio >= ceiling_ratio:
        return None
```

Driven on a 200 pixel span, the sampled curve measures 1.17972 times its chord
against the 1.18 asked for, sags 55.03 pixels, and lands exactly on both bots. A
wire between two bots in the same column has no span, and falls back to the
straight line between them.

`src/gui/main_tabs/wire_canvas_surface.py` — `catenary_curve`, the sample loop

```python
    for at in range(count):
        x_at = x_from + span * at / (count - 1)
        points.append([x_at, lift - a * math.cosh((x_at - vertex_x) / a)])
```

### No two flow-rate labels overlap

The percentage badge goes where the curve is flattest, which is the lowest point
of the hanging wire. Where that place is already taken, the badge walks outward
along the curve and then downward in 20 pixel steps until it is clear.

`src/gui/main_tabs/wire_canvas_surface.py` — `place_badge`

```python
    for at in badge_order(points, flattest):
        box = badge_rect(points[at], advance_px)
        if not any(rects_overlap(box, one) for one in placed):
            return box
```

Measured on a grid of 38 bots carrying 152 wires, with the real 33 pixel width of
a printed rate label: 114 pairs of badges sit on each other at the flattest
point, and none does after the walk. Both numbers come from the same run, so the
zero is a result rather than an empty instrument.

One painter each side reads one set of geometry. The Qt sheet imports the curve
and the placement from the same module the React payload is built from, so the
two cannot drift.

`src/gui/visualizer/wire_canvas.py` — what the Qt sheet imports

```python
from ..main_tabs.wire_canvas_surface import (
    arrow_points,
    catenary_curve,
    label_text,
    place_badge,
    point_at,
    pulse_percent,
    slack_for_offset,
)
```

Right-clicking a wire measures against the same curve, so the wire the pointer
finds is the wire on the screen.

### Qt against React

Twenty-two measured values were read off the Qt tab and out of the React payload
and compared: the card size, the grid columns and spacing, the repaint interval,
the theme count, the opacity slider, the absence of a View control, the tooltip,
the four stage names, labels, initials and floors, the tergite counts, the crown
spines, the wing spreads, the body scales, the stage colour table, the bot id
colour and the absent-growth text. Twenty-two of twenty-two matched. The
comparison reported one real difference on its first run, a grid of eight columns
on the Qt side against six on the React side, which is what it exists to catch.

## 2026-09-09 22:12 - #128 - the Swarm tab loses List View

The Swarm tab no longer offers a choice of view. The grid of locust cards is the
whole screen, and the View picker that used to sit between Theme and Wires is
gone from both builds. The table below carries the row for every file the change
touched; the rows in the table above are the state before it.

| Qt file | React module | Uses React | Bridge | Manifest | Registers in Electron | Ships in the build | RENDERS | Scope |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `src/gui/bot_swarm_list.py` | removed | - | - | - | - | - | - | deleted |
| `src/gui/bot_visualizer.py` | `bot_visualizer.js` | yes | yes | yes | yes | yes | yes | in scope |
| `src/gui/visualizer/bot_node.py` | `bot_node.js` | yes | yes | yes | yes | yes | yes | in scope |
| `src/gui/visualizer/wire_canvas.py` | `wire_canvas.js` | yes | yes | yes | yes | yes | yes | in scope |
| `src/gui/visualizer/growth_stage.py` | shared, no module of its own | - | - | - | - | yes | yes | in scope |
| `src/gui/react_bot_swarm_tab.py` | host for `bot_visualizer.js` | yes | yes | yes | yes | yes | yes | in scope |
| `src/gui/theme_engine.py` | `design_tokens.js` | - | yes | yes | yes | yes | yes | in scope |

The Qt widget file went. `BotListView` and `LaneWireCanvas` had one caller, the
Swarm tab, and nothing else built either of them. The live bot settings window
draws its own wire table from `QTableWidget`, so it lost nothing.

`src/gui/bot_swarm_list.py` — what was deleted

```python
class BotListView(QTableWidget):
class LaneWireCanvas(QWidget):
class BotSwarmLaneAllocator:
```

List View is removed whole. The surface `bot_swarm_list_surface.py` and the
module `bot_swarm_list.js` are deleted. The bridge method, the manifest line
and the renderer page's script tag that reached them are gone.

`src/gui/web/bot_swarm_tab.js` — the shell that still names the list globals

```javascript
  var LIST_API = "acervatorSwarmList";
  var LIST_LOADER = "acervatorLoadBotSwarmList";
```

Nothing defines those two globals now. The bot settings shell reads them in
four places and guards every read, so the list region draws nothing and
raises nothing.

`src/gui/react_bot_swarm_tab.py` — `TAB_SCRIPT_ASSETS`, the tail

```python
    "quick_routing.js",
    "bot_visualizer.js",
)
```

One control in `tools/conversion_state.py` named the deleted file. A control
pointed at a file that no longer exists reports `born React` rather than
`paired`, which reads as a pass and proves nothing, so it now names a Qt file
that is still paired.

`tools/conversion_state.py` — `CONTROLS`

```python
CONTROLS = ("bot_visualizer", "theme_engine", "design_tokens")
```

Both builds were opened with the change in place. Qt draws eight main tabs and
React draws ten, the same counts as before, and the Swarm tab in each carries no
View picker, no row list and no lane sheet.

Back to [the subsystem index](README.md).
