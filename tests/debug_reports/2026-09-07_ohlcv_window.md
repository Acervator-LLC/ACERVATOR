# The candle window now ends at the newest bar

One argument moved. The connector asked the venue for candles since the start of
1970 and took the oldest rows of the page it got back. It now asks for the count
it wants and takes the newest rows.

`~/.acervator/settings.json` hashed the same before and after, and no live
process was started, attached to or queried:

```
before  f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
after   f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
```

## The error

`ccxt.coinbase.fetch_ohlcv` takes four positional arguments. The third is the
start time and the fourth is the count. The connector passed the count third, so
the count landed in the start-time slot and the count slot was left empty.

```python
data = await self._call_sync(self._ex.fetch_ohlcv, symbol, timeframe, limit)
```

The library then fills the empty count slot with its own ceiling of 300, and
because a start time was given it keeps rows from the START of the page. The
venue sends up to 350 rows. Three hundred survive and the fifty newest are
dropped.

## Reproduction

The library's own slice ran over recorded five-minute pages from the Stone
Tablets. One argument differed between the two runs and nothing else.

```
ccxt 4.5.77   ccxt/base/exchange.py  filter_by_since_limit -> filter_by_limit
              a start time is present   ->  fromStart, rows 0 to 299 survive
              no start time             ->  rows 50 to 349 survive
```

Pages of 350 rows were taken from every stored pair, three per tablet.

```
pages driven                1215
before   offset in rows     -50 on 1215 of 1215,  300 rows returned
after    offset in rows       0 on 1215 of 1215,  100 rows returned
```

Counted in five-minute buckets rather than rows, the before arm reproduces the
spread the earlier audit recorded, because the venue sends no row for a bucket
with no trades:

```
before   -50 (121)  -51 (24)  -53 (21)  -54 (17)  -52 (13)  -56 (12)
after      0 on 1215 of 1215
```

The instrument is two-sided by construction. Zero pages read zero before the
change; every page reads zero after it.

## The correction

`src/exchange/ccxt_connector.py` — one call, four arguments, each in its own
slot.

```python
data = await self._call_sync(
    self._ex.fetch_ohlcv,
    symbol,
    timeframe,
    None if since is None else int(since),
    int(limit),
)
```

The branch that existed only to serve the wrong slot is gone. The docstring
described the wrong slot as a defect being left in place; it now describes what
the call does.

## The rerun, at the connector

`CCXTConnector.get_ohlcv` ran against `TabletBackend`, the ccxt-shaped surface
already in the tree, over real tablet rows. No network and no credential.

```
                asked 100   asked 250
before             300         300
after              100         250
```

## What the change does to a gate

One hundred and sixty two rows of the operator's own gate log carry a latched
gate, a band position and a band threshold, on a pair and a date the tablets
cover. `gate_healer.reconstruct_market_gate` rebuilt each row twice: once on the
window ending fifty bars early, once on the window ending at the bar the price
came from. No threshold was changed; each row's own `bb_upper_dt` and
`bb_lower_dt` were read back out of the log.

```
stale window reproduces the logged band position    72 of 162
current window reproduces it                         8 of 162
band latch differs between the two windows          88 of 162
  scrum band latched on the stale window, clear on the current   37
  scrum band clear on the stale window, latched on the current   13
```

The stale window reproduces his recorded number nine times more often than the
current one. That is the control: the number in the log was computed on candles
that had already fallen behind.

## The row count callers now receive

Every caller had been receiving the venue's page instead of what it asked for.
Eight of the ten now receive what they ask for.

| caller | asks | before | after |
| --- | --- | --- | --- |
| `src/exchange/data_pool.py:452` | 100 | 300 | 100 |
| `src/exchange/data_pool.py:696` | 100 | 300 | 100 |
| `src/trading/scrumming_bot.py:1821` | 100 | 300 | 100 |
| `src/trading/scrumming_bot.py:4258` | 100 | 300 | 100 |
| `src/exchange/chart_data.py:234` | 100 | 300 | 100 |
| `src/trading/phantom_balance.py:209` | 100 | 300 | 100 |
| `src/trading/ta_signal_provider.py:114` | 100 | 300 | 100 |
| `src/exchange/market_inspector_fetcher.py:187` | 200 | 300 | 200 |
| `src/exchange/market_inspector_fetcher.py:177` | 365 | 300 | 300 |
| `src/trading/stone_tablets/fetcher.py:124` | 350, with a start time | 300 | 300 |

The daily row at `market_inspector_fetcher.py:177` asks for more than the
library's ceiling, so its count does not move. Its window does: it had been the
oldest 300 rows of the page and is now the newest 300.

The tablet fetcher at `stone_tablets/fetcher.py:124` already supplied a start
time and is unchanged, which is why the recorded pages this report drives are
themselves unaffected.

## Fewer rows changes no indicator reading

A caller that asked for 100 and silently received 300 now receives 100. Running
the real voting engine and the real band detector on 300 bars and on 100 bars
ending at the SAME bar, over the same 162 rows:

```
direction differs            0 of 162
band position differs        0 of 162
control, end bar back one  161 of 162
```

The control moves the band position on all but one row, so the two zeros are
readings and not a blind instrument. The band is computed from the trailing
twenty closes, so a longer tail changes nothing. Only the end of the window
matters, and moving the end is the whole change.

## The test that pinned the old behaviour

`tests/test_tablet_backend_is_the_live_path.py` asserted that a caller asking
for 100 receives 300. Its invariant is that the tablet backend carries no rule
of its own and the connector's behaviour falls out of ccxt's real signature.
That invariant is unchanged, so the assertion was restated against it rather
than relaxed: three different limits are now requested and each must come back
at exactly the size asked for. A backend hardcoding any single number fails it.

```
against the old connector   1 failed, 17 passed
against this branch        18 passed
```

## The constant that named the old page

`EFFECTIVE_OHLCV_PAGE_SIZE` at `src/exchange/ccxt_connector.py:39` is read by no
code. Its comment said a live fetch returns the venue page rather than the
requested limit, which stops being true with this change. The comment now names
what the number is: the ceiling ccxt puts on one coinbase candle page.
