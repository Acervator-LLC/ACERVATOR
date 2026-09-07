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
isolated_tabs = {"Simulator", "Paper Trader"}
container = getattr(self, "_header_strip_container", None)
if container is not None:
    container.setVisible(tab_name not in isolated_tabs)
```

The surface module carries the same pair as a constant.

`src/gui/main_tabs/header_strip_surface.py` — `ISOLATED_TABS`

```python
ISOLATED_TABS = ("Simulator", "Paper Trader")
```

The Simulator draws its own strip in place of this one. `SimStatStrip` in
`src/gui/simulator_tab/sim_stat_strip.py` mirrors these ten fields against sim
balances.

## Bridge

The strip answers one bridge method, and one renderer module draws it.

`src/gui/main_tabs/header_strip_surface.py` — `METHOD`

```python
METHOD = "header.strip"
```

The renderer module is `header_strip.js`.

Back to [the subsystem index](README.md).
