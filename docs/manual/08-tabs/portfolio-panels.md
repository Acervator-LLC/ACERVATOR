# Portfolio Information Panels

Reference. The strip above the tab bar, present on every tab except the
two isolated ones.

## What builds it

One method builds the strip. It makes the window's central widget, lays a
single row across the top of it, and hands back the layout the tab row goes
into. That row holds the five spendable columns on the left and the five
counter cards on the right, and it does not move as you change tabs.

`src/gui/main_tabs/header_strip.py` — `HeaderStripMixin._build_header_strip`

```python
self._spendable_widget = SpendableProfitsWidget()
top_row.addWidget(self._spendable_widget, stretch=3)
```

## Left: the spendable columns

Five labelled columns fill the left half, divided by thin vertical rules.

| Column | Meaning |
| ------ | ------- |
| SPENDABLE | Cash the exchange reports, across the bots sharing one wallet |
| REALISED | Realised profit and loss |
| LOCKED | Value the open positions hold |
| MATURE | Wire profit old enough to move |
| EXCH | Connected exchange count |

The widget builds four of the five from one list, and each entry carries the
label the operator reads and the payload key that fills it.

`src/gui/widgets/spendable_profits.py` — `SpendableProfitsWidget.__init__`

```python
for label_text, key in [
    ("REALISED", "total_realised"),
    ("LOCKED", "locked"),
    ("MATURE", "mature"),
    ("EXCH", "exchanges"),
]:
```

One payload draws all five. A value the payload leaves out draws an em dash
rather than a zero, which keeps "no reading" and "a reading of nothing" apart.
That is the difference between a column with nothing behind it and a column
reporting a genuine zero, and on this strip it matters: two of the five have
nothing behind them today.

`src/gui/widgets/spendable_profits.py` — `SpendableProfitsWidget._money_text`

```python
@staticmethod
def _money_text(value) -> str:
    """Render one amount as money text, or as the empty marker."""
    amount = SpendableProfitsWidget._amount_of(value)
    if amount is None:
        return "—"
    return f"${amount:,.2f}"
```

REALISED and MATURE are the two. Both are handed a literal absence at the one
call site that fills the strip, so both draw the marker on every tick. The
Trading tab section carries the proposal for the first of them:
[06-trading-tab.md](../06-trading-tab.md).

Both now carry a figure, and the figure comes from the exchange. Realised is the
venue's own matched profit and loss across the fleet. Mature is the profit held
in positions worth more than three times what they cost, which is the growth
threshold the platform applies everywhere it decides maturity.

**Overtaken:** "Realised is the venue's own matched profit and loss across the
fleet."

The venue answers a cost basis, an average entry price and an unrealised
profit per spot position, and no lifetime realised figure. Realised is the
platform's own first in, first out match over the venue's own fills, one
figure per bot, added across the fleet.

**Overtaken:** "Mature is the profit held in positions worth more than three
times what they cost, which is the growth threshold the platform applies
everywhere it decides maturity."

Mature is the part of a position's value that sits over three times its cost.
A position worth $350 on a $100 cost basis holds $50 of mature profit. Three
times the cost is still the threshold the platform applies everywhere it
decides maturity.

`src/gui/main_tabs/header_strip_surface.py` — `profits_payload`

```python
"total_realised": exchange_amount(data, "total_realized_exchange"),
"mature": exchange_amount(data, "total_mature_exchange"),
```

Absence is still a reading. When the venue has answered for no bot, both columns
take nothing and draw the marker, and the mask leaves that marker alone. A hidden
figure shows four asterisks; an empty column stays empty under Privacy Mode.

`src/core/privacy_mask_registry.py` — `mask_or`

```python
text = str(value)
if field_id not in ALL_FIELD_IDS or text == ABSENT_TEXT:
    return text
```

### What the venue answers, and what the platform derives

The venue's portfolio breakdown answers three figures per open spot position:
the cost basis, the average entry price and the unrealised profit. Each bot
reads those three from the venue on every refresh and holds them as its own.
The breakdown carries no lifetime realised figure for a spot position, so
Realised is derived: every fill the venue holds for the bot's symbol, matched
first in, first out, one figure per bot, summed across the fleet.

`src/exchange/ccxt_connector.py` — `get_spot_positions`

```python
portfolios = await self._call_sync(self._ex.fetch_portfolios)
rows = await self._call_sync(self._ex.fetch_portfolio_details, uuid)
basis = float(row.get("cost_basis", 0) or 0)
```

The venue's cost basis is the check on the derivation. After the fills are
matched, the bot logs the venue's cost basis beside the cost of the buys FIFO
left open and beside the average-cost basis, with each gap in per cent, and
names the closer of the two. A venue whose account uses another matching method
shows up there as a gap on both.

`src/trading/scrumming/reconciliation.py` — `_log_basis_check`

```python
_fifo_gap = abs(_fifo - float(venue_basis)) / _scale
_avg_gap = abs(_avg - float(venue_basis)) / _scale
_closer = "fifo" if _fifo_gap <= _avg_gap else "average"
```

A venue without a portfolio breakdown leaves the three figures to the same
derivation, and the check does not run.

`src/exchange/position_health.py` — `compute_position_health`

```python
while sell_remaining > 1e-12 and buy_queue:
    buy_lot = buy_queue[0]
    take = min(buy_lot[0], sell_remaining)
    realized += (t.price - buy_lot[1]) * take
```

A sell is matched against the oldest open buy, so a sell placed above the latest
fold and below the first buy of a market that has fallen since lowers the
figure. Over the 2026 fill export, 1,302 of 2,653 sells lowered it and 66 were
priced under the most recent buy.

Each bot holds the complete fill history for its symbol. The first refresh pages
the venue newest to oldest until a page comes back short; every later refresh
fetches one page and stops at the first fill it already holds.

`src/exchange/fill_history.py` — `FillHistory.refresh`

```python
if len(fills) < FILL_PAGE_LIMIT:
    ended_short = True
    break
if joined:
    break
```

Before this, one call fetched the newest 500 fills and the figure was FIFO over
that window alone. On the two symbols past 500 fills the window read $-137.38
and $119.91 where the complete history reads $-390.53 and $60.27.

`src/trading/scrumming/reconciliation.py` — `refresh_exchange_position_health`

```python
_trades = await self.fetch_fill_history()
if _trades is None:
    return False
_asset_base = self.config.symbol.split("/")[0]
_ph = compute_position_health(_trades, _asset_base)
```

Mature applies one constant. A position counts once its value reaches its cost
plus two hundred per cent of its cost, and the column sums the profit on the
positions that qualify.

`src/trading/smart_wire.py` — `mature_profit_usd`

```python
MATURE_GROWTH_PCT: float = 200.0
if value < basis * (1.0 + MATURE_GROWTH_PCT / 100.0):
    return 0.0
return value - basis
```

**Overtaken:** "the column sums the profit on the positions that qualify."

The column adds up what each qualifying position holds over the threshold.
`mature_threshold_usd` is the cost plus two hundred per cent of the cost, and
`mature_profit_usd` answers the value above it.

`src/trading/smart_wire.py` — `mature_profit_usd`

```python
if not is_mature(cost_basis_usd, current_value_usd):
    return 0.0
return float(current_value_usd) - mature_threshold_usd(cost_basis_usd)
```

A position at three times its cost exactly is mature and holds nothing over
the threshold. `is_mature` carries that test on its own, so the count of
mature positions reads the position while the money column adds nothing for
it.

`src/trading/smart_wire.py` — `is_mature`

```python
threshold = mature_threshold_usd(cost_basis_usd)
if threshold <= 0.0:
    return False
return math.isfinite(value) and value >= threshold
```

### Realised reads the same on every start

A bot writes its realised figure only when the walk reached the end of the
venue's history. A walk that stops short keeps the last whole reading, writes
`stats.fill_history_complete` False and says so in the log, so the same fills
always answer the same figure.

`src/trading/scrumming/reconciliation.py` — `refresh_exchange_position_health`

```python
_complete = bool(getattr(self._fill_history, "complete", False))
self.stats.fill_history_complete = _complete
if _complete:
    self.stats.realized_pnl_exchange = float(_ph.realized_pnl_usd)
```

The fleet aggregate answers `realised_history_complete` False while any bot
the venue answered for reads False, and the column then draws the empty
marker. An absent figure never looks like a present one.

`src/gui/main_tabs/header_strip_surface.py` — `realised_amount`

```python
if not bool(data.get(REALISED_COMPLETE_KEY, True)):
    return None
```

The Paper and Simulator fleets walk no venue history, so their aggregates omit
the key and their realised figure passes through whole.

## Right: the five counter cards

Five cards close the row, and each one counts a single thing.

| Card | What it counts |
| ---- | -------------- |
| Scrummed | Cumulative USD sold across every bot since the process started |
| Folded | Cumulative USD bought across every bot since the process started |
| Trades | Executed buys and sells across the active bots |
| Bots | Bots in the RUNNING state |
| Errors | Errors across every bot since the last reset |

Errors is the one card you can click. Arming it takes one call, and the click
opens the rolling error buffer with its Reset button.

`src/gui/main_tabs/header_strip.py` — `HeaderStripMixin._build_header_strip`

```python
self._stat_errors.set_clickable(True, "Click to open the error log.")
self._stat_errors.clicked.connect(self._show_error_log_dialog)
```

Issue #428 carries a disagreement between what the tooltips on these cards
promise and what the cards draw.

A sixth card, P/L, is constructed and then hidden. Code that still writes to it
keeps working and nothing appears on screen.

`src/gui/main_tabs/header_strip.py` — `HeaderStripMixin._build_header_strip`

```python
self._stat_pnl = StatCard("P/L", "$0.00")
self._stat_pnl.setVisible(False)
```

The mode button on the right ends the row. `_toggle_trading_mode` swaps the
window between the crypto and stock layers.

## Privacy

Every field on the strip carries its own privacy dot. Attaching one registers
the field, and from then on the card draws its value through the mask.

`src/gui/main_tabs/header_strip.py` — `HeaderStripMixin._build_header_strip`

```python
self._stat_scrummed.attach_privacy_dot("counter.scrummed")
self._stat_folded.attach_privacy_dot("counter.folded")
self._stat_trades.attach_privacy_dot("counter.trades")
self._stat_bots.attach_privacy_dot("counter.bots")
self._stat_errors.attach_privacy_dot("counter.errors")
```

The registry behind those field ids is shared. Hide a field here and the same
field hides on the Bot Swarm tab, because both surfaces ask the one registry.

`src/core/privacy_mask_registry.py` — `mask_or`

```python
def mask_or(value, field_id: str, mask: str = "****") -> str:
    """Return ``mask`` when ``field_id`` is masked, else ``str(value)``.

    A ``field_id`` outside ``ALL_FIELD_IDS`` never masks, which covers every
    ``TA_FIELD_IDS_EXCLUDED`` entry.
    """
```

## Where the numbers come from

One aggregate call fills the whole strip, once a tick. Every card and every
column is written from that single answer, so two cards cannot disagree about
the same fleet.

`src/gui/main_window.py` — `_refresh_dashboard`

```python
agg = self._bot_manager.get_aggregate_stats()
_scr = float(agg.get("total_scrummed_usd", 0.0) or 0.0)
_fld = float(agg.get("total_folded_usd", 0.0) or 0.0)
self._stat_scrummed.set_value(f"${_scr:,.2f}")
self._stat_folded.set_value(f"${_fld:,.2f}")
```

The aggregate itself is `FleetAggregationMixin.get_aggregate_stats` in
`src/trading/container/aggregation.py`.

## Hiding

Two screens are isolated from live trading, and on those two the strip hides
itself. The absent strip is the signal: no live numbers are on this screen.

`src/gui/main_window.py` — `_on_main_tab_changed`

```python
isolated_tabs = set(ISOLATED_TABS)
container = getattr(self, "_header_strip_container", None)
if container is not None:
    container.setVisible(tab_name not in isolated_tabs)
```

The window surface carries the same pair as a constant, and issue #450 renamed
both labels.

`src/gui/main_tabs/main_window_surface.py` — `ISOLATED_TABS`

```python
ISOLATED_TABS = (SIM_TAB, PAPER_TAB)
```

The Simulator draws its own strip in place of this one. `SimStatStrip` in
`src/gui/simulator_tab/sim_stat_strip.py` mirrors these ten fields against sim
balances.
The Simulator rebuild removed this file; it is not in the tree.

### The strip stays on Sim and reads the sim fleet

The Simulator rebuild took the Sim tab out of the isolated pair, so the strip
hides on Paper alone. On Sim the same ten fields carry the Simulator's
figures, read from the Sim tab's fleet source, and the live fleet's numbers do
not reach the strip while Sim is in front. The window picks the fleet on every
tick and on every tab change.

`src/gui/main_tabs/main_window_surface.py` — the two tuples

```python
ISOLATED_TABS = (PAPER_TAB,)

#: The tabs the header strip reads the Simulator's fleet on, not the live one.
SIM_FED_TABS = (SIM_TAB,)
```

`src/gui/main_window.py` — `_refresh_header_strip`

```python
if self._header_strip_reads_sim():
    sim_tab = self._simulator_tab
    self._write_header_strip(
        sim_tab.fleet_source().aggregate(), sim_tab.exchange_count()
    )
    return
```

[simulator.md](simulator.md) covers what each field reads on Sim.

## Bridge

The strip answers one bridge method, and one renderer module draws it.

`src/gui/main_tabs/header_strip_surface.py` — `METHOD`

```python
METHOD = "header.strip"
```

The renderer module is `header_strip.js`.

Back to [the subsystem index](README.md).
