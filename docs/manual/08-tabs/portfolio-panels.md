# Portfolio Information Panels

Reference. The strip above the tab bar, present on every tab except the
two isolated ones.

## What builds it

`HeaderStripMixin._build_header_strip` in
`src/gui/main_tabs/header_strip.py` creates the window's central widget
and returns the layout the main tab widget goes into. The strip is one
row.

## Left: the spendable columns

`SpendableProfitsWidget` in `src/gui/widgets/spendable_profits.py` draws
five labelled columns divided by thin vertical rules:

| Column | Meaning |
| ------ | ------- |
| SPENDABLE | Cash the exchange reports, across the bots sharing one wallet |
| REALISED | Realised profit and loss |
| LOCKED | Value the open positions hold |
| MATURE | Wire profit old enough to move |
| EXCH | Connected exchange count |

`update_profits` takes one payload dict and renders it. A value the
payload omits draws an em dash rather than a zero, which keeps "no
reading" and "a reading of nothing" apart.

## Right: the five counter cards

`StatCard` in `src/gui/widgets/dashboard_stat_card.py` draws each card.

| Card | What it counts |
| ---- | -------------- |
| Scrummed | Cumulative USD sold across every bot since the process started |
| Folded | Cumulative USD bought across every bot since the process started |
| Trades | Executed buys and sells across the active bots |
| Bots | Bots in the RUNNING state |
| Errors | Errors across every bot since the last reset |

The Errors card is clickable. `set_clickable` arms it and the click
reaches `_show_error_log_dialog` in `src/gui/main_window.py`, which opens
the rolling error buffer and its Reset button.

A sixth card, P/L, stays constructed and hidden. Code paths that still
call `_stat_pnl.set_value` keep working while the card draws nothing.

The mode button on the right ends the row. `_toggle_trading_mode` swaps
the window between the crypto and stock layers.

## Privacy

Every field carries a privacy dot. `attach_privacy_dot` registers the
field id, `mask_or` in `src/core/privacy_mask_registry.py` substitutes
the mask on the next render, and the registry is shared, so a toggle on
this strip also hides the same field on the Bot Swarm tab.

## Where the numbers come from

`_refresh_dashboard` in `src/gui/main_window.py` calls
`BotManager.get_aggregate_stats`, defined as
`FleetAggregationMixin.get_aggregate_stats` in
`src/trading/container/aggregation.py`, then writes each card and calls
`update_profits`. One aggregate feeds every field, so two cards cannot
disagree about the same fleet.

## Hiding

`_on_main_tab_changed` hides the strip's container while the active tab
is Simulator or Paper Trader. `ISOLATED_TABS` in
`src/gui/main_tabs/header_strip_surface.py` carries the same pair. The
Simulator draws its own strip instead: `SimStatStrip` in
`src/gui/simulator_tab/sim_stat_strip.py` mirrors these ten fields
against sim balances, and the missing live strip is itself the signal
that the screen is not live trading.

## Bridge

`header_strip_surface.view_model` answers the `header.strip` method in
the registry that `build_registry` in `src/core/desktop_bridge.py`
assembles. The renderer module is `header_strip.js`.

Back to [the subsystem index](README.md).
