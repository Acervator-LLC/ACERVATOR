# The fifty-candle lag in the TA window

Explanation. It answers one question and changes no live behaviour.

## The question

A live gate row carries a price and a set of candle-derived numbers. Validation
reproduced those numbers from the recorded tape, but only from a candle window
that ends fifty five-minute bars earlier. Fifty bars is four hours and ten
minutes. This page names where the candles fall behind the price, and proves the
mechanism on recorded data.

```
recorded rows reproduced from the tape   141 of 141
offset that reproduces them              -50 bars (117), -51 (23), -84 (1)
window offsets -4 to +4                  no offset fits better
rollups 5m, 15m, 30m, 1h, 2h, 4h, 1d     no timeframe fits better
all 38 live bots read the 5m timeframe   from the saved fleet
```

## Where the two values part company

One method takes both. It reads the price, then reads the candles, then hands
the candles to the indicators. The price is at most five seconds old. The candle
list is already fifty bars old when it arrives. The band position the gate
compares is the close of the last candle in that list, never the price.

```
src/trading/scrumming_bot.py:2559   async def tick
src/trading/scrumming_bot.py:2639     ticker  = await self._get_ticker(symbol)
src/trading/scrumming_bot.py:2827     candles = await self._get_ohlcv(symbol, ta_tf, limit=100)
src/trading/scrumming_bot.py:2877     bb_result = detect_bb_proximity(candles, ...)
src/trading/indicators/bb_proximity.py:71    price = closes[-1]
src/exchange/data_pool.py:114       ticker entry goes stale after 5 seconds
```

## The lag is already there when the connector returns

The connector writes its own record of every candle call, and that record holds
the close of the newest bar it received. Pairing that close against the ticker
price for the same pair dates the newest bar. This audit reads three console log
rotations, covering 2026-09-06 18:35 to 2026-09-07 20:39, and searches time
shifts from minus 300 to plus 400 minutes for the best fit.

```
pair          best shift        error against the shift of zero
PENGU/USD     249 min  (49.8 bars)   20x lower
AERO/USDC     247 min  (49.4 bars)   27x lower
CAP/USD       261 min  (52.2 bars)    8x lower
BILL/USD      294 min  (58.8 bars)    4x lower
WLFI/USDC     295 min  (59.0 bars)    4x lower
LSETH/USDC      0 min                 unchanged — this pair barely moves and
                                      cannot answer the question
negative shifts were worse at every step, so the candles trail the price
```

The connector writes that record itself, before any cache holds the data. The
window already trails by fifty bars at the moment the connector hands it over.

## What the venue page loses

The venue sends up to 350 bars in one page. The exchange library caps a page at
300. The live call passes the candle count as the third positional argument,
which is the library's start-time slot, not its count slot. The library reads
that as a start time, keeps the OLDEST 300 rows of the 350, and discards the 50
newest.

```
src/exchange/ccxt_connector.py:937
    data = await self._call_sync(self._ex.fetch_ohlcv, symbol, timeframe, limit)
                                                                 the start-time slot

inside the exchange library, the slice that follows
    a start time is present   ->  keep from the start of the page
    keep 300 of 350           ->  rows 0 to 299 survive, rows 300 to 349 are dropped

venue page cap of 350 is stated at src/trading/stone_tablets/fetcher.py:107
350 - 300 = 50
```

## The number, driven on recorded candles

Driving the library's own slice with 350 recorded five-minute bars from the
stored price history gives two results. One argument differs between the runs,
and nothing else.

```
recorded page                    350 rows, newest bar 2026-08-01T18:35
live argument, start time set    300 rows, newest bar 2026-08-01T14:25   -50 bars
control, start time unset        300 rows, newest bar 2026-08-01T18:35     0 bars
```

The same slice then ran over 1,205 pages taken from every stored pair. The
offsets it produced carry the same shape as the recorded rows.

```
-50    329 pages
-51     59 pages
-52     32 pages
tail   thinly traded pairs reach -84 and further
```

The mode sits at fifty because fifty rows are always dropped. The tail is wider
because the venue sends no row for a five-minute bucket that had no trades, so
fifty dropped rows can span more than fifty buckets. That is why the recorded
rows cluster at fifty and one of them sits at eighty-four.

## What it is not

Four other readings fail against the code and against the logs. Each of them
sits downstream of the connector record that dates the lag.

```
a cache lifetime     a five-minute entry lives 300 seconds, one bar, not fifty
                     src/exchange/data_pool.py:25 and :65
a window built once  the whole list is replaced on every refresh
                     src/exchange/data_pool.py:452
a starved refresh    59,452 candle calls in one 12-hour log; the median gap
                     between calls for one pair is 311 seconds
an empty result      0 of 59,452 calls returned no data; every one returned 300 rows
```

## What a fix would change

The change is one line. Pass the candle count in the library's count slot and
leave the start time unset. The library then keeps the newest rows of the page
instead of the oldest, and the connector returns a window that ends on the bar
that just closed.

PROPOSED — `src/exchange/ccxt_connector.py:937`

```python
data = await self._call_sync(
    self._ex.fetch_ohlcv, symbol, timeframe, None, limit
)
```

Every gate on every bot would then read candles from the same moment as the
price. Today a scrum or fold gate compares a band position built from candles
that closed four hours and ten minutes ago against a price from this second.
After the change both describe the same minute. The band position in a gate row
moves, the trend and consensus votes move with it, and gates that latch on the
band latch at different times. This unit leaves the line alone for that reason:
the change moves every gate decision on bots trading real money.

One further finding, named and left alone. The constant naming the venue page
size at `src/exchange/ccxt_connector.py:39` says 300, no code reads it, and the
venue page is 350.

## Provenance

This unit started, attached to and queried no live process. It read the runtime
tree and never wrote it.

```
settings.json before   f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
settings.json after    f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
```
