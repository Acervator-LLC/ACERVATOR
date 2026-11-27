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

### The venue call queue a refresh shares

One connector serves every bot on a venue and runs a single worker, so every
caller on that venue shares one call queue eight deep. The eight are the reads
outside an order's step. An order's calls go ahead of them and are not counted, as
[the next section](#a-call-that-waits-its-turn-and-a-call-that-never-answers)
describes. A refresh asks for one symbol at a time, and before each ask it waits
until six or fewer of those reads wait or run. The
balance, ticker, portfolio and OHLCV reads the running platform polls therefore
take the worker first. Past its budget of 60 seconds the ask goes through at once,
and a full queue can refuse it.

`src/exchange/ccxt_connector.py` — `CCXTConnector.await_bulk_read_slot`

```python
if free and self._sync_queue_depth <= BULK_READ_ADMIT_DEPTH:
    break
if time.monotonic() - start >= budget_sec:
    break
await asyncio.sleep(BULK_READ_WAIT_SLICE_SEC)
```

`src/exchange/history_helpers.py` — `_await_slot`

Measured on a fleet of thirty-nine bots on one venue, with two hundred platform
reads issued while a refresh ran: forty-seven of those reads were refused at the
queue's cap while the refresh held the worker back to back, and six once the
refresh waited its turn. The same two hundred reads with no refresh running at
all were refused five times, so the refresh now costs the platform about one
read where it used to cost forty-two. Both runs returned the same 8,558 rows.

A refusal at the cap costs a symbol its rows, so one refused submission earns a
second wait.

`src/exchange/history_helpers.py` — `BULK_READ_ATTEMPTS`

```python
BULK_READ_ATTEMPTS = 2
```

A venue that does not serialise its calls needs no turn-taking, and the default
waits for nothing.

`src/exchange/base.py` — `ExchangeInterface.await_bulk_read_slot`

```python
del budget_sec
return 0.0
```

### A call that waits its turn, and a call that never answers

The worker runs one call at a time. Two lines wait for it. An order, a cancel and
each read inside an order's step stand in the first line, and every other read
stands in the second. The worker starts the first call of the first line, and the
first call of the second line only while the first line is empty. Each line keeps
the order its calls were asked in. So an order waits for the call that runs and for
the orders asked before it, and never for a read that has not started.

`src/exchange/ccxt_connector.py, in SyncWorker._serve_next`

```python
job, call = (self._goes_first or self._gives_way).pop(0)
```

A read keeps its place in the queue until
the worker reaches it or its caller stops waiting. A caller waits up to 102
seconds for a read's turn, retries included. That is a full queue of eight calls
at 12.8 seconds each, the slowest call to the venue's time endpoint measured on a
saturated link. An order or a cancel waits up
to 25 seconds, and so does each try of a read inside an order's step. A call that
misses its turn is not sent.

`src/exchange/ccxt_connector.py, in SyncCall.to_venue`

```python
if reads and not in_order_turn():
    return cls(name, run, reads, read_turn_left_sec(), missed=TurnMissed)
return cls(
    name, run, reads, ORDER_TURN_WAIT_SEC, goes_first=True, counted=False
)
```

The limit of eight counts the second line alone. A read asked behind eight others
is refused at once, and a line of reads refuses no call of the first line.

`src/exchange/ccxt_connector.py, in CCXTConnector._call_sync_timed`

```python
if call.counted and self._sync_queue_depth >= SYNC_QUEUE_CAP:
```

A step of an order is the bot's own function that reads for an order and sends it:
a fold, a sale, a rebalance, a detonation, Self-Destruct, Fire, the Extractor's
Fire, and each poll of an order. The mark holds for the task that runs the step. A
task the step starts reads in the second line, and so do the holdings audit and the
look at the account after a fill, which no order waits on.

`src/exchange/base.py, in in_order_turn`

```python
task = _ORDER_TASK.get()
return task is not None and task is asyncio.current_task()
```

The limit on one call is 25 seconds, and it starts when the worker starts the
call. A slow answer inside the limit comes back, and its worker keeps the queue.
A call with no answer at the limit is stuck. Its caller reads an error at that
moment, and a fresh worker takes the queue.

`src/exchange/ccxt_connector.py, in SyncWorker.stuck_call`

```python
call = self.running
return call if call is not None and call.run_left_sec() <= 0.0 else None
```

Each read that waited behind the stuck call moves to the fresh worker, the reads
of an order's step first and each line in the order it was asked, and goes to the
venue once. An order or a cancel that waited there
is dropped and is never sent. A stuck order is not sent again. A stuck read is
tried again by its caller, up to three tries in all.

`src/exchange/ccxt_connector.py, in CCXTConnector._replace_stuck_worker`

```python
if fresh is not None and call.keeps_turn:
    fresh.take(call)
else:
    call.dropped = True
```

### The markets the shared price read asks for

One read refills the stored prices of an exchange. It starts each 2.5 seconds for
each exchange the fleet uses while that exchange answers quickly, and it hands the
connector the markets that have a stored price. Each row that comes back refills its
own market. A market the answer leaves out keeps its last price. Behind slow answers
the read starts later, as [the pace of the shared reads](#the-pace-of-the-shared-reads)
describes.

`src/exchange/data_pool.py, in MarketDataPool.refresh_all_tickers`

```python
return await reader(asked)
```

Coinbase takes the markets by name, in one request. A market goes by the id in
the market list the connector loaded, and a market that list does not hold goes
by its two codes. Coinbase answers the ids it lists and leaves out the rest, so a
market it does not list costs no other market its price. A contract is never
named, and its price comes from its own bot's read.

`src/exchange/ccxt_connector.py, in CCXTConnector._ticker_ids`

```python
market = markets.get(symbol) or {}
asked = str(market.get("id") or named.unloaded_id(symbol))
if asked and not is_contract_market(market):
    ids[asked] = None
```

The read asks for every market instead, in one request, in four cases:

- on every exchange but Coinbase;
- for a request address longer than 8,000 characters;
- once 15 minutes have passed since every market was last read;
- after Coinbase refused a read by name, or answered it with no row.

`src/exchange/ccxt_connector.py, in CCXTConnector._named_ticker_params`

```python
if symbols is None or named is None or self._every_ticker_due():
    return None
ids = self._ticker_ids(symbols, named)
if not named.fits(ids):
    return None
```

The 24 hour volume of a market with no stored price comes from a read of every
market. One price answer on Coinbase carries no volume, so the connector gives
the volume its last read of that market recorded, and before any read the one in
the loaded market list. The Extractor ranks its watch list by it. The Market
Inspector always asks for every market.

`src/exchange/ccxt_connector.py, in CCXTConnector._quote_volume_for`

```python
recorded = self._quote_volumes.get(symbol)
if recorded is not None:
    return float(recorded)
markets = getattr(self._ex, "markets", None) or {}
return record_quote_volume(markets.get(symbol))
```

### The moment a price was read

Each price carries the moment the venue answered it. The worker marks that moment
when the call comes back, so a price that waits for the program grows older while it
waits. Each row of a shared answer carries the moment of that answer.

`src/exchange/ccxt_connector.py, in answered_at`

```python
return ReadMoment.at_monotonic(timing.finished_at)
```

A stored price takes an answer and its moment together. An answer older than the one
it holds changes nothing. A price served after a refused call carries the moment of
the answer it came from, so it is never read as new.

`src/exchange/data_pool.py, in TickerEntry.take`

```python
if self.read_at is not None and ticker.read_at.before(self.read_at):
    return False
```

The dollar rate of a quote keeps its moment in the same way. The bot reads the rate
again once it is over 5 seconds old. An order reads both ages against one limit, which
[An order and the age of its price](../06-trading-tab.md#an-order-and-the-age-of-its-price)
describes.

`src/trading/scrumming_bot.py, in ScrummingBot._refresh_quote_to_usd`

```python
self._quote_to_usd = rate
self._quote_rate_read_at = usd_ticker.read_at
```

### The pace of the shared reads

Each exchange the fleet uses has its own loop. The loop reads the prices, then the
account, and then rests. A slow exchange does not slow another. While the two answers
take 1.67 seconds or less together, the loop starts again each 2.5 seconds. Longer
answers make the rest longer. The rest is at least half the time the two reads held
the worker, so the shared reads hold it for two thirds of the time at most.

`src/exchange/data_pool.py, in SharedReads.period_s`

```python
own = max(self.interval_s, self.held_s * TURN_PER_HELD_SECOND)
return max(own, min(own * BACKOFF_FACTOR**self.steps, longest_period_s()))
```

That time is counted on the worker. A pause of the program does not add to it, and
the wait in the queue does not. At 6.3 seconds an answer the two reads start each
18.9 seconds. A stored price then stays under 20 seconds, as long as no other call
stands in the queue in front of them. Two answers of more than 13 seconds together
make it older. The [Current Position Value](../06-trading-tab.md#the-bot-tables) cell
is then blank, and
[no order starts on it](../06-trading-tab.md#an-order-and-the-age-of-its-price).

A throttled answer doubles the time between two turns of the loop, to 5, 10 and 20
seconds, and a read with no answer does the same. A good answer halves it. The 20 is
the age limit of a price, and a smaller stored limit ends the doubling there. The Price
Age Limit row of [Settings > Trading](settings.md#settings--trading) sets that limit. Where a
throttled answer names a wait, the loop keeps that wait, up to 300 seconds. After a
read with no answer the loop rests 20 seconds at most. A shared read is sent once, and
the next one is the next try. After the first good answer the loop is back at 2.5
seconds inside 15 seconds, with no restart and no press.

`src/exchange/data_pool.py, in SharedReads.note_failed`

```python
if label == VENUE_LOST:
    self.lost_at[kind] = time.monotonic()
else:
    stated = min(stated_wait_seconds(exc), DEFAULT_MAX_COOLOFF_S)
    self.wait_until = max(self.wait_until, time.monotonic() + stated)
```

### What a bot does while a shared read is late

A bot whose stored price or balance has passed its lifetime asks the venue nothing
while a shared read is on its way or due, outside an order's step. While the venue
throttles or gives no
answer, the bot waits for the next shared read. It looks again at each step of the
program and takes the new figure from the store. The wait ends after 60 seconds. The
bot then asks alone, or its read ends in an error and the next tick tries again.

`src/exchange/data_pool.py, in SharedReads.awaited`

```python
if self.slowed():
    return True
soon = self.due_at - now <= sum(self.answer_s.values())
return now < ends_at and (bool(self.reading) or soon)
```

A figure inside its lifetime waits for the next shared read too, outside an order's
step, once it is older than 2.5 seconds and older than the two newest answers
together.

`src/exchange/data_pool.py, in SharedReads.replaces`

```python
answers_s = sum(self.answer_s.values())
return age_s > max(self.interval_s, answers_s + self.min_rest_s)
```

A bot asks the venue alone where no shared read serves it:

- a new market, between two shared reads;
- a market the shared answer leaves out;
- a balance that a fill has just ended;
- a shared read the venue refuses;
- shared prices that are lost while the venue answers other calls;
- an exchange with no such loop.

One price and one account read go out alone at a time for each exchange, outside an
order's step. Each waits for two free places in the queue, so the last place stays
for a shared read.

`src/exchange/data_pool.py, in MarketDataPool._ask_alone`

```python
token = self._take_turn(turn, label)
if token is None or reads.places.take(connector, SPARE_PLACES):
    return token
```

A candle read waits for two free places as well, 60 seconds at most, and then asks.
A shared read waits for one free place.

`src/exchange/data_pool.py, in MarketDataPool._await_place`

```python
places = self.shared_reads(exchange_id).places
ends_at = time.monotonic() + SHARED_WAIT_SECONDS
while not places.take(connector, spare) and time.monotonic() < ends_at:
    await asyncio.sleep(SHARED_WAIT_SLICE_SECONDS)
```

A step of an order waits for none of this. It takes a stored price or balance inside
its lifetime, or it asks the venue at once, and the worker starts that read ahead of
every read outside a step.

`src/exchange/data_pool.py, in MarketDataPool._turn_to_ask`

```python
if in_order_turn():
    return None if served() else object()
```

### The pairs the pairs scout asks for

The window calls the pairs scout each 2 seconds, and while a reading is on its way
the newest call waits for it. The scout keeps one book of pairs
for each exchange. The two Target columns of the bot table and the two Target rows
of the Detail window ask it for one base at a time, and it keeps each ask for 15
minutes. The Market Inspector's proposals read every book whole.

`src/exchange/market_pairs_scout.py, in MarketPairsScout._note_ask`

```python
venue = ANY_EXCHANGE if exchange_id is None else exchange_id
self.asked[(venue, base, quote)] = time.monotonic()
```

On Coinbase a reading asks by name. It names each base a row asked for in four
quotes: the dollar, its stablecoin and the two coins of the Target columns. One
call names 200 pairs at most. A pair Coinbase does not list costs no other pair its
price. A pair the answer leaves out leaves the book. An exchange that takes no
names gets one call for every market. It gets no call where a read of every market
landed in the last 10 seconds or is on its way.

`src/exchange/market_pairs_scout.py, in MarketPairsScout._pairs_asked`

```python
quotes = {*READER_QUOTES, quote} - {base}
names.update(f"{base}/{one}" for one in quotes)
```

A reading by name does not reset the 15 minutes of the shared price read. The first
read by name after them asks for every market, and one such read is on its way at a
time. The connector keeps its last answer that held every market, and the scout
takes that answer into its book. A proposal reads a figure up to 15 minutes old for
a market that no row asks for.

`src/exchange/market_pairs_scout.py, in MarketPairsScout._take_every_ticker`

```python
read_at, rows = answer()
if read_at <= self.last_refresh(exchange_id):
    return False
self.ingest_tickers(exchange_id, rows, now=read_at)
```

Each call waits for a free place in the queue, 20 seconds at most. With no free
place the book stays, and the next call of the window starts again. After a reading
the exchange rests 10 seconds, or twice the time its answers took where that is
longer. After a failed reading it rests 20 seconds or more. One call earns a rest
of 50 seconds at most. So the scout holds the worker of one exchange for a third of
the time at most. A book stays under 20 seconds old while the answers of one reading
take 6 seconds or less, and it grows older behind slower ones.

`src/exchange/market_pairs_scout.py, in MarketPairsScout._read`

```python
rest = max(shortest_rest, REST_PER_ANSWER * took)
book.rest_until = time.monotonic() + rest
```

Each exchange has a reading of its own. No second one starts beside it, and no
exchange waits for another. The window waits for the reading, and ends it only at a
limit, a close, a disconnect or a locked fleet; see
[the venue reads a window tick starts](console.md#the-venue-reads-a-window-tick-starts).
A scout at rest has not stopped. A scout that stops shares its books, its asks and the
reading on its way with its replacement.

`src/exchange/market_pairs_scout.py, in MarketPairsScout.hold_books`

```python
self.books = other.books
self.asked = other.asked
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
[the Simulator tab](simulator.md#the-ytd-trade-files) for the file format and the reader.

The import reads the export through a column map chosen by the exchange id it
is given. One map exists, for Coinbase, and a Coinbase export writes the same
files it always did. An exchange with no map is refused by name, with a line
saying a sample export is needed, and nothing is written.
[The Simulator tab](simulator.md#the-ytd-trade-files) says how the Simulator reads what the map writes.

`src/exchange/ytd_csv_import.py` — the map chosen at import

```python
def import_ytd_csv(
    csv_path: Path,
    exchange_id: str,
    root: Optional[Path] = None,
) -> ImportResult:
    """Read ``csv_path`` and write ``exchange_id``'s trade files under
    ``get_ytd_root(root)``."""
    column_map = export_map_for(exchange_id)
```

### The platform's own line for each fill

The platform also keeps its own record. Every fill a bot books writes one line
to `trade.log` in the log folder. A fill that settles in several pieces writes
one line for each piece, and the pieces of one order carry the same order id.
Each line names the venue order the piece settled. It also names the event id
of each tranche the fill spent and of each tranche it opened.

A scrum, a manual sale and a DIST sale open fold tranches. A buy that opens a
stack ladder opens stack tranches. A fold, a cartridge buy, a Manual Fire, a
detonation, a self-destruct and a stack sale spend them.

`src/core/emit_contracts.py, in SettledFill`

```python
    venue_order_id: str = ""
    spent_event_ids: tuple[str, ...] = ()
    opened_event_ids: tuple[str, ...] = ()
    fee_usd: Optional[float] = None
    fee_refusal: Optional[str] = None
    target_growth: Optional[TargetGrowth] = None
```

A line written before these fields existed holds none of them, and it still
loads. `src/trading/live_log_reader.py, in _validate_trade_entry` requires only
the old fields, and checks the type of a new field where a line holds one.

### The figures of a target increase

A fold that runs the growth step writes its figures on the line of the fill
that caused it, under `target_growth`. The figures are the units bought, the
units at scrum, the fill price, the fee percent, the wire share, the gain, the
quote rate, the surplus, the standing pool, the cycle cap, the cap already used,
the cap room, the growth applied, the pool after and the new target. The wire
share is the one a Manual Fire reads, and 0 where a fold reads none.

The bot log line of the same step names the same order. So a target increase
joins the fill that caused it by the order id.

`src/trading/scrumming_bot.py, in ScrummingBot._apply_fold_target_growth`

```python
        cap_room = fold_cap_remaining_usd(cycle_cap, consumed)
        applied, standing_after = target_growth_applied(surplus_usd, standing, cap_room)
```

The engine holds no copy of this arithmetic: `target_growth_applied` is the one
rule. A surplus or a pool that is not a finite number counts as zero. A cap room
that is not a finite number counts as used. When the surplus and the pool are
both within one billionth of a dollar, nothing moves.

`src/trading/scrumming/sizing.py, in target_growth_applied`

```python
    surplus = max(0.0, finite_reading(surplus_usd))
    standing = max(0.0, finite_reading(standing_usd))
    if surplus <= GROWTH_DUST_USD and standing <= GROWTH_DUST_USD:
        return 0.0, standing
```

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

One sentence above is overtaken. Quoted whole:

> One function returns the rendered page: the rows plus the pager state. It is
> the only disk read on that path.

The page builder still returns the rows and the pager state. It makes no disk
read when the tab draws, because the tab hands it both join indexes. The tab
reads the logs once per fetch, on its own thread, and the page builder's own
read only runs for a caller that supplies neither index.

Now: the tab reads the logs once per fetch, in steps of about 8 ms on the window thread, after the first page draws (`src/gui/history_tab.py, in join_steps`).

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

The footer's two strings follow the same rule. The contract declares the page
counter and the summary line, and the tab calls the contract for both, so one
arithmetic produces each string for every surface that draws it.

`src/exchange/history_read_contract.py` — `page_label`, the counter the tab
calls

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

Each trade is joined to its gate entry by `lookup_gate_entry` in
`src/exchange/history_helpers.py`. One threshold decides what counts as a
match, and a trade with no entry inside it reads "no record" in the cell.

`src/exchange/history_helpers.py` — the join threshold

```python
JOIN_TOLERANCE_SECONDS = 60.0
"""Largest gap ``_best_entry_within_window`` accepts between a trade and a log
entry, and the backdate the index builders apply to ``since``."""
```

Nothing measures coverage across a window.

`build_page_voting_index` and `lookup_voting_entry` do the same for the
indicator voting snapshot behind each trade.

## When the logs are read

The tab reads the gate log and the voting log once, when a fetch lands, on a
thread of its own. Drawing a page and pressing Prev or Next read the indexes
already in hand and touch no file.

Now: the read waits until the first page draws, then runs in steps of about 8 ms on the window thread (`src/gui/history_tab.py, in HistoryTab._start_join_index_build`).

`src/gui/history_tab.py` — `HistoryTab._start_join_index_build`

```python
def _start_join_index_build(self) -> None:
    """Read the gate and voting indexes for ``_all_trades`` off this thread.

    ``_render_page`` then reads the held indexes, so no page draw and no
    pager press touches disk; the newest build wins and an older
    build's answer is dropped.
    """
```

The read keeps only the minutes a cell can ask for. A lookup reads a trade's
own minute and the two beside it, so an entry in any other minute can never
reach a cell and is not held.

`src/gui/history_tab.py` — `join_bucket_keys`

```python
def join_bucket_keys(rows: list, bot_manager) -> set:
    """The ``(bot_id, minute)`` keys the gate and voting lookups can reach.

    ``lookup_gate_entry`` reads a row's own minute and the two beside it, so an
    index holding only these keys answers every lookup identically.
    """
```

Measured on the operator's own logs, with a six-megabyte active gate log, five
rotated copies of fifty-two megabytes each and a sixteen-megabyte voting log:
3,494 rows over 35 pages. The gate read kept 2,895 minutes and the voting read
2,955, against 167,944 gate entries parsed before. The longest stretch in which
the window could not repaint fell from 4.2 seconds to 0.06, which is what an
idle window reads on the same instrument. Every Gates cell and every light row
on four sampled pages matched the earlier values exactly.

Nothing paces the fetch itself. One tab activation asks the venue for fills
once per bot symbol, and those calls share one worker thread and a queue of
eight with every other venue reader on the platform.

`src/exchange/ccxt_connector.py` — the shared queue

```python
SYNC_QUEUE_CAP: int = 8
```

## The renderer

`HistoryWebTable` in `src/gui/react_history_panel.py` draws the table with
React inside the Chromium PySide6 ships, and sits where the Qt table used to.
One History tab, one renderer, one set of rows.

The Qt table takes no theme. The React table takes one because it builds its page
in that theme, and the Qt table's chrome comes from the application stylesheet
instead, so a theme handed to it reached no colour. The tab passes neither.

`src/gui/history_qt_table.py` — `HistoryQtTable`, what construction takes

```python
        def __init__(self, parent=None) -> None:
            super().__init__(parent)
            self.setAccessibleName("Qt History Table")
            self._last_model: dict = {}
```

Driven with one row and two columns, 26 values read back off the real table under
Cyberpunk Dark and then Neon Light: every colour and every string was identical and
the only value that moved was the theme name the table had stored. The React table,
driven the same two ways, moves all six of its page colours.

## The Simulator front-load

Refreshing History hands the Simulator the year of live trades it needs before
a parity run. The tab's signal connects to the Simulator's panel, and the
builder makes that connection once both tabs exist.

`src/gui/history_tab.py` — `HistoryTab.history_refreshed`

```python
history_refreshed = Signal(list)
```

Now: the signal is a `Signal(object)`, so it hands the rows over without converting them (`src/gui/history_tab.py, in HistoryTab.history_refreshed`).

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

## 2026-09-08 08:17 - no issue recorded - what the closed issues landed

The History Tab is able to pull trade history from all active exchanges via their respective APIs. It also pairs each imported trade with its in-platform trading logic and applies our trade grading system.

The tab keeps the name History. It sits eighth on the bar, on the gold
ground with red text.

The tab fetches from every active venue and draws the rows with React. Every
cell value comes from one read contract; the table renders those fields and
derives none, which stops a second History growing behind the renderer.

`src/exchange/history_read_contract.py` — `build_page`

```python
def build_page(
    filtered: list[dict],
    page: int = 0,
    bot_manager: Any = None,
    gate_index: Optional[dict] = None,
    voting_index: Optional[dict] = None,
) -> HistoryPage:
```

The grade comes from the trade grader and the gate lights come from the same
vocabulary the Simulator's gate cell reads. A refresh also hands the Simulator
its year of live trades, so the tab's signal front-loads the parity run.

![The History tab: filters, graded rows and the gate lights.](p32-i0.png)

The Filters group carries From and To date pickers, then Exchange, Symbol and
Side, each filled from the rows in hand. Apply narrows the set, Reset restores
it, and Refresh goes back to the venues. The line under the group counts the
retained rows against the loaded rows, both sides with their dollar totals, and
the age of the last fetch.

Thirteen columns carry a row, newest first, and nothing re-sorts. BUY draws
green and SELL red.

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

Grade, Gates and Voting close the set.

The Gates cell opens with the blocker text, then the lights. Nineteen of them:
the ten scrum gates TGT, INT, BB, FIRE, TA, LS, TRND, HTF, CB and OTD, then the
nine fold gates BB, MID, TA, LS, TRNQ, CEIL, HTF, CB and OTD. Each light draws
under its own label, and each bank ends with an `S` or an `F` marker. Five
states, five colours.

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

Green passed, red the gate that blocked, amber not armed for another reason,
grey not evaluated at this candle, and cyan a landing-strip override. The
blocker text and the light banks overlap in the figure; both occupy the one
cell.

One sentence above is overtaken. Quoted whole:

> The blocker text and the light banks overlap in the figure; both occupy the one
> cell.

The blocker text and the light banks share the one cell and no longer overlap.
The Qt table writes the text once, into the lights cell's own label, and leaves
the table item under that cell blank. A row whose gate log holds no entry has no
lights cell, and there the table item carries the `no record` text itself.

Prev, the page counter and Next page the result at the foot, and Export CSV
writes the current selection out. The read contract declares both footer
strings, and the tab calls it for both, so the counter and the summary read the
same on this tab as on the React panel.

History Tab (React):

![](p32-i1.png)

The same tab, captured while the asynchronous fetch runs. Five fixed status
strings cover the states before any row exists, and the one on screen is the
fetching entry.

`src/exchange/history_read_contract.py` — `STATUS_TEXT`

```python
STATUS_TEXT = {
    "idle": "No history loaded yet — click Refresh.",
    "no_bot_manager": "Bot manager unavailable — cannot fetch history.",
    "no_async_loop": "Async loop not ready — try again after platform starts.",
    "fetching": "Fetching trade history from exchanges…",
    "timeout": "Fetch timeout (300s). Exchange may be rate-limited; try again.",
}
```

Two constants bound the fetch, in the same module: the poll runs on a 400 ms
timer, so an observed latency is the true latency plus up to one interval, and
the fetch is abandoned after three hundred seconds. At that limit the fetch is
cancelled, so a second Refresh has no earlier fetch beside it.

`src/exchange/history_read_contract.py` — the fetch bounds

```python
FETCH_POLL_INTERVAL_S = 0.4
```

The header strip is visible here, which marks the screen as a live-trading tab.
REALISED and MATURE draw the exchange figures the Live tab draws, which issue
#418 fed. A row whose gate log holds no entry inside the join window reads
`no record`.

Both columns draw an exchange figure here too, because one strip serves every
tab that shows it. Where the venue has answered for no bot they stay empty, and
Privacy Mode leaves an empty column empty.


### Trade grading

The grader scores a trade that has already happened. It never feeds a trading
decision, it never tunes a parameter, and no gate consults it. The same inputs
always give the same grade.

Four axes are scored. An axis with no input is skipped: it neither credits nor
penalises, and the overall number is the unweighted mean of the rest.

`src/trading/trade_grader.py` — `grade_trade`

```python
exec_score, exec_bps = _score_execution(record, ctx)
timing_score, mfe, mae = _score_timing(record, ctx)
strategic_score, sb_delta = _score_strategic(record, ctx)
outcome_score, realized = _score_outcome(record, ctx)
```

| Axis | What it reads | What a 1.0 means |
| ---- | ------------- | ---------------- |
| Execution | fill price against the reference price at decision time | no slippage |
| Timing | the favourable excursion against the adverse one over the following candles | the trade went far more right than wrong before it closed |
| Strategic | the asset's discipline ratio before the trade against after it | the trade moved the ratio the operator's way |
| Outcome | realised profit per unit | a clear gain |

The regime tag reaches the grade and the rationale string and gets no score of
its own. Grading the same record with a regime tag and without one returns the
same number, which is the control that proves it.

The scale is 0.0 to 1.0, not 0 to 100, and the mean becomes a letter at fixed
boundaries.

`src/trading/trade_grader.py` — `_letter_from_numeric`

```python
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

Driving the mapper across each boundary and just under it flips the letter
exactly where the code says, in both directions.

**One trap worth knowing.** A trade with no gradeable input at all scores 0.5
and therefore reads as a **D**, not as ungraded. A fully specified trade scores
1.0 and reads A+. A column of Ds may mean the trades were poor, or it may mean
the surrounding price context never arrived.

## 2026-10-06 - #1133 - the trade historian's own fetch

Refresh is not the only thing that asks the venue for fills. A launch also
runs the trade historian, once for every market in the fleet, and the
historian calls the venue directly rather than through the connector's
paced read path.

`src/core/trade_historian.py` — the call

```python
trades = self._exchange.fetch_my_trades(symbol, limit=limit) or []
```

### The published limit

Coinbase publishes the limit for the private fills endpoint as ten requests
per second per profile, with bursts up to twenty. One fetch every hundred
milliseconds sits on that published figure, and the platform derives the
interval from it rather than picking a number.

`src/core/trade_historian.py` — the interval

```python
PUBLISHED_FILLS_RPS = 10.0
HISTORY_FETCH_INTERVAL_S = 1.0 / PUBLISHED_FILLS_RPS
```

The gate is one object for the whole program, so every market's fetch
queues behind the last one. A second connector's threads wait their turn
in the same queue, which is what keeps the request rate at the published
figure no matter how many connectors a launch builds.

`src/core/trade_historian.py` — the gate

```python
_FETCH_GATE = _HistoryFetchGate(HISTORY_FETCH_INTERVAL_S)
```

### A refused fetch

A venue can refuse for reasons the platform does not control, so a refusal
is tried again. The historian uses the retry the exchange paths already
share: three attempts, doubling the wait each time, and only for the error
classes that name a transient condition.

`src/core/trade_historian.py` — the attempt budget

```python
HISTORY_FETCH_ATTEMPTS = 3
HISTORY_RETRY_BASE_DELAY_S = 1.0
```

A refusal is the venue answering normally, so it records nothing about the
connection. Nothing on this path writes the lost-connection state that
turns a venue's row red in Settings, and that state keeps its one writer in
the credential validator.

`src/exchange/credential_state.py` — the lost-connection writer

```python
def record_connection_lost(
    exchange_id: Any, when: Any = None, path: Any = None
) -> bool:
```

Once every attempt is spent the market gets no history, and the line above
the table says so with the count.

`src/core/trade_historian.py` — the line

```python
MISSING_HISTORY_FORMAT = (
    "Trade history missing for {refused} of {scanned} markets — "
    "the venue refused the fetch."
)
```

One sentence above is overtaken. Quoted whole:

> The read contract declares both footer strings, and the tab calls it for both, so the counter and the summary read the
> same on this tab as on the React panel.

The read contract still declares both footer strings and the tab still calls
it for both. When a history fetch has been refused the Qt tab appends the
missing-history line to the summary it got back, so on that one state the
summary reads longer here than on the React panel.

`src/gui/history_tab.py` — the append

```python
missing = self.missing_history_status()
self._set_status(f"{summary}  {missing}" if missing else summary)
```

Back to [the subsystem index](README.md).
