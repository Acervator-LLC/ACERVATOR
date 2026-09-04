# History Tab

Reference. Trade history pulled from the venues, paired with the platform's
own trading logic and graded.

## What builds it

`HistoryTabMixin._build_history_tab` in
`src/gui/main_tabs/history_tab.py` constructs `HistoryTab` from
`src/gui/history_tab.py` and hands it the bot manager.

## Fetching

`refresh` starts `_kick_async_fetch`, which asks every active exchange
for the operator's own fills.
`fetch_all_history_chunked` in `src/exchange/history_helpers.py` walks
each exchange and symbol pair the bot manager exposes and
`normalize_trade` turns each venue trade into one row dict.

The exchange is the authority here. The rows on screen are the venue's
answer, and the platform's own log joins to them rather than replacing
them.

`_on_main_tab_changed` in `src/gui/main_window.py` refreshes the tab on
activation when the last fetch is older than five minutes and no fetch is
already in flight.

## Filtering, paging, export

`_populate_filter_options` fills the exchange, symbol and side pickers
from the rows in hand. `_apply_filters` narrows them, `_reset_filters`
restores the full set, and `_current_filters` reports the active state.
`_remember_to_bound` and `_to_bound_ts` hold the upper date bound across a
refresh. `_render_page`, `_prev_page` and `_next_page` page the result,
and `_export_csv` writes the current selection out.

## Where the cell values come from

`build_page` in `src/exchange/history_read_contract.py` returns
`HistoryRow` records. Thirteen `COLUMNS` each yield one `HistoryCell`
carrying a value, its text, its colour and its tooltip. `ROW_ORDER` is
the whole ordering contract. Nothing in that module writes or emits.

The table renders those fields and derives none of them. A cost, a grade,
a colour or a gate light on screen is always the contract's answer, which
is what keeps a second implementation of History from growing behind the
renderer.

## Grading

`grade_trade` in `src/trading/trade_grader.py` takes one `TradeRecord`
and a `PriceContext` and averages the sub-scores from `_score_execution`,
`_score_timing`, `_score_strategic` and `_score_outcome`, skipping any
axis that lacks inputs. `_letter_from_numeric` turns that unweighted mean
into `A+`, `A`, `B`, `C`, `D` or `F`. `grade_trades` runs the batch.
`PriceContext.regime_tag` reaches the grade's regime and rationale
without a sub-score of its own.

## Gate analysis

`build_page_gate_index` in `src/exchange/history_helpers.py` buckets the
gate log entries by bot id and minute, `lookup_gate_entry` picks the
closest one to a trade, and `gate_cell_text` and `gate_cell_tooltip`
render the cell. `gate_light_row` in `src/trading/gate_vocabulary.py`
turns a gate state into the row of lights.

That vocabulary is shared on purpose. The Simulator's `GateLightsCell`
and this table read the same labels and the same blocker prefixes, so a
gate added on one surface cannot be missing from the other. That shared
seam is what makes the Simulator's gate comparison meaningful.

Coverage across a window is `classify_trades` in
`src/trading/gate_coverage.py`. Every trade gets one status and the
report counts only the trades that found a gate. `DEFAULT_TOLERANCE_S` is
one five-minute candle either side; `LOG_GAP_THRESHOLD_S` separates a
logging gap from a genuine absence. `compute_validation_window` turns
coverage into the window the run can be judged over.

`build_page_voting_index` and `lookup_voting_entry` do the same for the
indicator voting snapshot behind each trade.

## The renderer

`HistoryWebTable` in `src/gui/react_history_panel.py` draws the table
with React inside the Chromium PySide6 ships, and sits where the Qt table
used to. One History tab, one renderer, one set of rows.

## The Simulator front-load

`HistoryTab.history_refreshed` connects to
`FleetReplayPanel.on_history_refreshed`, so refreshing History hands the
Simulator the year's live trades it needs before a parity run. The
builder makes the connection once both tabs exist.

## Paper History

The manual's part list names a Paper History Tab beside this one. No such
module has ever been committed. See [paper-trader.md](paper-trader.md)
for the proof.

## Bridge

`history_surface.view_model` in `src/exchange/history_surface.py` answers
`history.view_model` and assembles the whole screen from the read
contract; `history_tab_surface` answers `history_tab.chrome` and
`react_history_panel_surface` answers `react_history_panel.state`. The
renderer modules are `history_tab.js`, `history_panel.js` and
`history_panel.css`.

Back to [the subsystem index](README.md).
