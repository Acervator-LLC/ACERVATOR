# History Tab

Reference. Trade history pulled from the venues, paired with the platform's
own trading logic and graded.

## What builds it

One builder makes the tab, adds it to the row, and hands it the bot manager.

`src/gui/main_tabs/history_tab.py` — `HistoryTabMixin._build_history_tab`

```python
def _build_history_tab(self) -> None:
    """Build the History tab and add it to the main tab widget."""
```

## Fetching

Refresh starts an asynchronous fetch that asks every active exchange for the
operator's own fills. The helper walks each exchange and symbol pair the bot
manager exposes, and turns each venue trade into one row.

`src/exchange/history_helpers.py` — `fetch_all_history_chunked`

```python
async def fetch_all_history_chunked(
```

The exchange is the authority here. The rows on screen are the venue's answer,
and the platform's own log joins to them rather than replacing them.

The tab refreshes itself on activation when the last fetch is older than five
minutes and no fetch is already in flight.

`src/gui/main_window.py` — `_on_main_tab_changed`

```python
is_stale = last_ts == 0 or _t.time() - last_ts > 300
if is_stale and not in_flight:
    hist.refresh()
```

## Where the trade record is kept

Refresh reads the venue live and keeps nothing. The year of trades the Simulator
needs is kept separately, on disk, under the exchange history bucket. One file
holds one exchange, one symbol and one year, and every file names its exchange
inside itself.

`src/core/log_paths.py` — the bucket

```python
def get_exchange_history_dir() -> Path:
    """``exchange_history/`` bucket — the YTD trade files.
```

The files are filled from a transactions CSV exported from the exchange. The
import keeps buys and sells, counts and drops everything that is not a trade,
and refuses a file that is missing a column it needs. Re-importing an
overlapping export adds only the rows whose id is new.

`src/exchange/ytd_csv_import.py` — the import

```python
def import_ytd_csv(
    csv_path: Path,
    exchange_id: str,
    root: Optional[Path] = None,
) -> ImportResult:
    """Read ``csv_path`` and write ``exchange_id``'s trade files under
    ``get_ytd_root(root)``."""
```

Where the export covers a period and carries no trade for a symbol in it, that
period is written to a gap record rather than filled. See
[the Simulator tab](simulator.md) for the file format and the reader.

## Filtering, paging, export

Eight methods carry the controls under the table.

| Method | What it does |
| ------ | ------------ |
| `_populate_filter_options` | Fills the exchange, symbol and side pickers from the rows in hand |
| `_apply_filters` | Narrows the set |
| `_reset_filters` | Restores the full set |
| `_current_filters` | Reports the active state |
| `_remember_to_bound`, `_to_bound_ts` | Hold the upper date bound across a refresh |
| `_render_page`, `_prev_page`, `_next_page` | Page the result |
| `_export_csv` | Writes the current selection out |

## Where the cell values come from

One function returns the rendered page: the rows plus the pager state. It is
the only disk read on that path.

`src/exchange/history_read_contract.py` — `build_page`

```python
def build_page(
    filtered: list[dict],
    page: int = 0,
    bot_manager: Any = None,
    gate_index: Optional[dict] = None,
    voting_index: Optional[dict] = None,
) -> HistoryPage:
    """One rendered page: the ``HistoryRow`` list plus the pager state.

    ``build_join_indexes`` runs when neither index is supplied, and it is the
    only disk read on this path.
    """
```

Thirteen columns each yield one cell carrying a value, its text, its colour and
its tooltip.

`src/exchange/history_read_contract.py` — `COLUMNS`, the first ten

```python
COLUMNS: tuple[HistoryColumn, ...] = (
    HistoryColumn(0, "timestamp", "Timestamp (UTC)"),
    HistoryColumn(1, "exchange", "Exchange"),
    HistoryColumn(2, "symbol", "Symbol"),
    HistoryColumn(3, "bot", "Bot"),
    HistoryColumn(4, "side", "Side"),
    HistoryColumn(5, "amount", "Amount"),
    HistoryColumn(6, "price", "Price"),
    HistoryColumn(7, "cost", "Cost USD"),
    HistoryColumn(8, "fee", "Fee"),
    HistoryColumn(9, "trade_id", "Trade ID"),
```

Grade, Gates and Voting close the set. The ordering is fixed newest-first and
nothing re-sorts.

`src/exchange/history_read_contract.py` — `ROW_ORDER`

```python
ROW_ORDER = "timestamp_desc"
"""Newest first. ``fetch_all_history_chunked`` sorts ``reverse=True``,
``HistoryTab`` calls no ``setSortingEnabled``, and nothing re-sorts."""
```

The table renders those fields and derives none of them. A cost, a grade, a
colour or a gate light on screen is always the contract's answer, which is what
keeps a second implementation of History from growing behind the renderer.

Two strings depart from that pattern. The contract already declares the summary
line and the page counter, and the tab builds both itself, so two
implementations of the same two strings stand in the tree. Issue #425 carries
it.

`src/exchange/history_read_contract.py` — `page_label`, the declaration the tab
does not call

```python
def page_label(page: int, total: int) -> str:
    """The footer's page counter, or "No matches" when ``total`` is zero."""
    if total == 0:
        return "No matches"
    page = clamp_page(page, total)
    return f"Page {page + 1} / {page_count(total)} ({total} trades)"
```

## Grading

One record and its price context go in, and an unweighted mean comes out. An
axis with no input is skipped, so it neither credits nor penalises.

`src/trading/trade_grader.py` — `grade_trade`

```python
def grade_trade(record: TradeRecord, ctx: PriceContext) -> TradeGrade:
    """Grade one ``record`` against its ``ctx``.

    ``TradeGrade.overall_numeric`` is the unweighted mean of the sub-scores
    whose inputs were present, or 0.5 when no axis could be scored.
    """
    exec_score, exec_bps = _score_execution(record, ctx)
    timing_score, mfe, mae = _score_timing(record, ctx)
    strategic_score, sb_delta = _score_strategic(record, ctx)
    outcome_score, realized = _score_outcome(record, ctx)
```

The mean becomes a letter at fixed boundaries.

`src/trading/trade_grader.py` — `_letter_from_numeric`

```python
def _letter_from_numeric(num: float) -> str:
    """Map ``num`` in [0.0, 1.0] to ``A+``, ``A``, ``B``, ``C``, ``D`` or ``F``."""
    if num >= 0.93:
        return "A+"
    elif num >= 0.85:
        return "A"
    elif num >= 0.70:
        return "B"
    elif num >= 0.55:
        return "C"
    elif num >= 0.40:
        return "D"
    else:
        return "F"
```

`grade_trades` runs the batch. The regime tag reaches the grade's regime and
its rationale without a sub-score of its own.

## Gate analysis

Four helpers in `src/exchange/history_helpers.py` join the gate log to a trade.

| Helper | What it does |
| ------ | ------------ |
| `build_page_gate_index` | Buckets the gate log entries by bot id and minute |
| `lookup_gate_entry` | Picks the closest entry to a trade |
| `gate_cell_text` | Renders the cell text |
| `gate_cell_tooltip` | Renders its tooltip |

The lights themselves come from one vocabulary. Nineteen of them, the scrum
bank then the fold, each carrying its bank marker, its label, its state and its
colour. No Qt type crosses that boundary.

`src/trading/gate_vocabulary.py` — `gate_light_row`

```python
def gate_light_row(
    scrum_armed: bool,
    fold_armed: bool,
    scrum_blockers: Optional[list] = None,
    fold_blockers: Optional[list] = None,
    landing_strip_side: str = "",
    evaluated: bool = True,
) -> list[dict]:
    """The nineteen lights, in draw order: the scrum bank then the fold.

    Each entry carries ``bank`` ("S" or "F"), ``label``, ``state`` and
    ``color``. Serialisable: no Qt type crosses this boundary.
    """
```

Five states, five colours.

`src/trading/gate_vocabulary.py` — `LIGHT_COLORS`

```python
LIGHT_COLORS: dict[str, str] = {
    "override": "#22d3ee",
    "not_evaluated": "#333340",
    "blocked": "#ff3366",
    "passed": "#00cc55",
    "not_the_blocker": "#c8901e",
}
```

That vocabulary is shared on purpose. The Simulator's gate cell and this table
read the same labels and the same blocker prefixes, so a gate added on one
surface cannot be missing from the other. That shared seam is what makes the
Simulator's gate comparison meaningful.

Coverage across a window is `classify_trades` in
`src/trading/gate_coverage.py`. Every trade gets one status and the report
counts only the trades that found a gate. Two thresholds decide what counts as
a match and what counts as a hole in the log.

`src/trading/gate_coverage.py` — the two thresholds

```python
DEFAULT_TOLERANCE_S: float = 300.0
"""One 5m candle either side of a trade, the window ``_nearest`` searches."""

LOG_GAP_THRESHOLD_S: float = 1800.0
"""Six 5m candles of silence, above which ``_in_log_gap`` returns True."""
```

`compute_validation_window` turns coverage into the window the run can be
judged over.

`build_page_voting_index` and `lookup_voting_entry` do the same for the
indicator voting snapshot behind each trade.

## The renderer

`HistoryWebTable` in `src/gui/react_history_panel.py` draws the table with
React inside the Chromium PySide6 ships, and sits where the Qt table used to.
One History tab, one renderer, one set of rows.

## The Simulator front-load

Refreshing History hands the Simulator the year of live trades it needs before
a parity run. The tab's signal connects to the Simulator's panel, and the
builder makes that connection once both tabs exist.

`src/gui/history_tab.py` — `HistoryTab.history_refreshed`

```python
history_refreshed = Signal(list)
```

## Paper History

The manual's part list names a Paper History Tab beside this one. No such
module exists. Issue #19 built the Paper tab and its log, so the ledger such a
tab would read is on disk now, and no screen reads it. See
[paper-trader.md](paper-trader.md).

## Bridge

Three methods serve this screen.

| Bridge method | Serves |
| ------------- | ------ |
| `history.view_model` | The whole screen, assembled from the read contract |
| `history_tab.chrome` | The surrounding controls |
| `react_history_panel.state` | The table |

Three renderer files draw it: `history_tab.js` for the chrome, then
`history_panel.js` and its stylesheet for the table.

Back to [the subsystem index](README.md).
