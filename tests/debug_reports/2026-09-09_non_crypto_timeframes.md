# The non-crypto timeframe rotation

**Mode: Debug report.** Six program errors, each reproduced, diagnosed,
corrected and run again. Every run drove Scan Now over the FOREX major sector.

Nothing was posted. No account and no credential was used. Every price read is
public market data, taken sparingly from one endpoint.

`~/.acervator/settings.json` hashed the same before and after:
`18D380C7134DADBB2ACBF5CBE5527EA177FE8B23CC77EB3FFF6334FB03FEEAC8`.

## What the operator asked for

Issue #407, section 8, names four timeframes per asset class.

```
Crypto                        5m    1hr    1d    1wk
Stocks and other asset groups       1hr    1d    1wk    1mnth
```

This unit is the second row. The first row is a separate unit and is untouched.

## The caller, on a pdb stack

Scan Now reaches the venue through eight product frames. The breakpoint sits in
the adapter and fires only when the timeframe is not the daily one.

```
break src/trading/stone_tablets/ra_fetcher.py:246, str(timeframe) != '1d'
p (asset, timeframe, interval)
('EURUSD=X', '1h', '1h')
```

The frames between the button and the fetch, innermost last:

```
ata_spm.py(1114)  scan_now      -> sectors, added, found = self.compute(
ata_spm.py(1084)  compute       -> run(
ata_spm.py(970)   run           -> scans = evaluate(...)
ata_spm.py(646)   evaluate      -> _scan_timeframe(voter, assets, timeframe, ...)
ata_spm.py(669)   _scan_timefr. -> candles = candles_for(candle_source, ...)
ata_spm.py(562)   candles_for   -> return list(candle_source(symbol, timeframe)...)
market_inspector_surface.py(1974) sector_candles -> ata_asset_maps.venue_candles(
ata_asset_maps.py(249) venue_candles -> attempt = asyncio.run(
ra_fetcher.py(246) fetch_chunk  -> end_ms = int(until_ms) + DAY_MS
```

## Error one — three of the four timeframes never ran

### The rotation that did not run

A FOREX scan read seven pairs on the daily timeframe only. The other three
boxes were reported as unserved, so three quarters of the rotation produced
nothing.

```
VENUE_TIMEFRAMES: {'yahoo': ('1d',), 'exchange': ('1d', '1w')}
sector: major forex assets: 7
  unserved: ('1h', '1w', '1M')
  tf 1d votes 7 unread 0
report: Phase 1 Evaluate: 1 sector(s), 0 call(s), 0 chart(s)
```

### Reproducing the missing timeframes

A driver pressed Scan Now on the FOREX major sector, through the shipped board.

```
python -X dev -X faulthandler <driver>
PYTHONWARNINGS=error
```

### Why the adapter refused them

The venue table listed one timeframe for the chart endpoint, and the adapter
refused every other key by name.

`src/trading/stone_tablets/ra_fetcher.py` — the refusal, before this unit

```python
if timeframe != RA_TIMEFRAME:
    return FetchAttempt(
        since_ms=since_ms,
        until_ms=until_ms,
        error=f"{self.exchange_id} serves {RA_TIMEFRAME} only, not {timeframe}",
    )
```

The refusal was a module constant, not a limit of the endpoint. The endpoint
serves more.

### The interval table

The adapter reads a table of the intervals it serves, and the venue table is
built from that same table so the two cannot drift.

`src/trading/stone_tablets/ra_fetcher.py` — the intervals served

```python
YAHOO_INTERVALS: dict[str, str] = {
    "1h": "1h",
    RA_TIMEFRAME: "1d",
    "1w": "1wk",
    "1M": "1mo",
}
```

`src/trading/ata_asset_maps.py` — the venue table, derived from it

```python
VENUE_TIMEFRAMES: dict[str, tuple[str, ...]] = {
    VENUE_YAHOO: tuple(YAHOO_INTERVALS),
    VENUE_EXCHANGE: (RA_TIMEFRAME, "1w"),
}
```

### The scan, after the table

All four timeframes vote, nothing is unserved, and the run reaches phase three.

```
VENUE_TIMEFRAMES: {'yahoo': ('1h', '1d', '1w', '1M'), 'exchange': ('1d', '1w')}
  unserved: () deferred: ()
  tf 1h votes 7   tf 1d votes 7   tf 1w votes 7   tf 1M votes 7
report: Phase 3 Pull: 1 sector(s), 1 call(s), 1 chart(s)
```

## Error two — the weekly and monthly keys are not the endpoint's own words

### The refused week and month

The engine names its timeframes with one set of words and the endpoint reads
another. Passing the engine's word straight through returns a refusal.

```
  1w REFUSED HTTPError: HTTP Error 400: Bad Request
  1M REFUSED HTTPError: HTTP Error 400: Bad Request
```

### Reproducing the refusal

One ticker was asked for on each candidate word, over a twenty-five year
window, through the module's own request helper.

### Why the words differ

The endpoint spells a week as `1wk` and a month as `1mo`. The engine spells them
`1w` and `1M`. The old adapter had no translation because it only ever sent one
word.

### The translation

The interval table above is the translation. The key is the engine's word and
the value is the endpoint's word.

### The week and month, after the translation

Both answer, back to the ticker's own listing date.

```
 1wk rows=  1190 first=2003-12-01 last=2026-09-09 span=8318.1d granularity=1wk
 1mo rows=   275 first=2003-12-01 last=2026-09-09 span=8318.1d granularity=1mo
```

## Error three — an hourly window longer than 729 days is refused

### The refused hourly window

The hourly interval answered nothing at all on a long window, and the failure
was a refusal rather than an empty answer.

```
ask  1000d REFUSED HTTPError: HTTP Error 422: Unprocessable Entity
ask   800d REFUSED HTTPError: HTTP Error 422: Unprocessable Entity
ask   730d REFUSED HTTPError: HTTP Error 422: Unprocessable Entity
ask   729d rows=12506 first=2024-09-10 01:00 last=2026-09-09 01:32 span=729.0d
```

### Reproducing the long hourly ask

The same ticker was asked for hourly candles over six window lengths, in one
run, one second apart.

### Why 730 days fails

The endpoint caps intraday history. The boundary is 729 days: 729 answers and
730 refuses. Nothing in the tree knew that, so a long hourly ask returned no
candles instead of the candles that exist.

### The reach, and the clamp

Each interval carries the days it reaches. A capped interval has its start moved
forward to the oldest bar it can answer, so the request always returns the rows
that exist.

`src/trading/stone_tablets/ra_fetcher.py` — the reach, and the clamp

```python
YAHOO_REACH_DAYS: dict[str, int] = {
    "1h": 729,
    RA_TIMEFRAME: UNCAPPED_REACH_DAYS,
    "1w": UNCAPPED_REACH_DAYS,
    "1M": UNCAPPED_REACH_DAYS,
}


@staticmethod
def reach_start_ms(timeframe: str, since_ms: int, end_ms: int) -> int:
    reach = YAHOO_REACH_DAYS.get(timeframe, UNCAPPED_REACH_DAYS)
    if reach == UNCAPPED_REACH_DAYS:
        return int(since_ms)
    return max(int(since_ms), int(end_ms) - reach * DAY_MS)
```

The other three answered a twenty-five year request in full, so no cap was
measured for them and none is claimed.

### What each interval reaches

Each interval is asked over a window sized from its own bar length, and each
reports what it reached. This is the whole answer to "what history does each
interval have".

```
floor to vote: 30
 1h asked    16d rows=  286 first=2026-08-24 02:00 last=2026-09-09 01:00 reached= 16.0d
 1d asked   365d rows=  248 first=2025-09-10 00:00 last=2026-09-09 00:00 reached=364.0d
 1w asked  1400d rows=  197 first=2022-11-14 00:00 last=2026-09-09 01:44 reached=1395.1d
 1M asked  6000d rows=  197 first=2010-04-30 23:00 last=2026-09-09 01:44 reached=5975.1d
```

**Hourly reaches sixteen days and the others reach years.** That is normal for
intraday data and it is stated per interval rather than hidden. All four clear
the thirty-candle floor.

**The daily row count is lower than the days asked for.** Currency pairs carry
no weekend bar, so 365 days of calendar time hold 248 trading days.

**The ask is the bar target times the bar length.** Two bar targets already
existed in the tree and both are reused; no third number is introduced.

`src/trading/ata_asset_maps.py` — the two tables the window comes from

```python
TIMEFRAME_BAR_DAYS: dict[str, float] = {
    "1h": 1.0 / 24.0,
    RA_TIMEFRAME: 1.0,
    "1w": 7.0,
    "1M": 30.0,
}

TIMEFRAME_BARS_ASKED: dict[str, int] = {
    "1h": DAILY_BARS,
    RA_TIMEFRAME: DAILY_BARS,
    "1w": WEEKLY_BARS,
    "1M": WEEKLY_BARS,
}
```

## Error four — every hourly bar floored onto midnight

### The collapsed hourly timestamps

The row reader moved every timestamp back to the midnight of its own day. On an
hourly series that puts a whole day of bars on one timestamp.

```
endpoint stamps: 290
read as 1h: rows 287 distinct ts 286
read as 1d: rows 265 distinct ts 14
```

Two hundred and sixty-five rows sat on fourteen timestamps.

### Reproducing the collapse

One hourly response was read twice, by the shipped reader, once at the hourly
key and once at the daily default.

### Why one flooring rule was wrong

The reader had one flooring rule because it had one timeframe. A day is the
wrong period for an hourly bar.

### The step per interval

Each interval floors to its own step. A week and a month have no fixed step, so
their stamps are kept exactly as the endpoint sent them.

`src/trading/stone_tablets/ra_fetcher.py` — the step per interval

```python
YAHOO_STEP_MS: dict[str, int] = {"1h": HOUR_MS, RA_TIMEFRAME: DAY_MS}
```

### The stamps, after the step

Every interval now returns one row per period.

```
 1h rows=  286 distinct=  286
 1d rows=  248 distinct=  248
 1w rows=  197 distinct=  197
 1M rows=  197 distinct=  197
```

## Error five — the running hour arrived twice

### The hour that arrived twice

The hourly series carried one timestamp twice. The endpoint sends the period in
progress as its own row, stamped at market time, beside the completed row for
the same hour.

```
 1h rows=  287 distinct=  286 tail=['2026-09-09 00:00', '2026-09-09 01:00', '2026-09-09 01:00']
```

### Reproducing the duplicate

Rows and distinct timestamps were counted for all four intervals in one run.
Only the hourly interval disagreed.

### Why only the hourly interval

Both rows floor onto the same hour. The other three intervals do not floor, so
their running period keeps a stamp of its own and never collides.

### One row per period

A floored interval keeps one row per timestamp, and keeps the last. The last is
the newer reading of that period. Nothing is averaged and no bar is invented.

`src/trading/stone_tablets/ra_fetcher.py` — one row per period

```python
def _last_per_stamp(rows: list[list[float]]) -> list[list[float]]:
    """One row per timestamp, keeping the last, oldest first.

    A running period the endpoint sends twice floors onto one ``YAHOO_STEP_MS``
    step, so ``_rows_from_series`` would otherwise carry both.
    """
    held: dict[float, list[float]] = {}
    for row in rows:
        held[row[0]] = row
    return [held[ts] for ts in sorted(held)]
```

### The rows, after keeping one

The hourly duplicate is gone and the daily answer is byte-identical.

```
 1h rows=  286 distinct=  286 tail=['2026-09-08 23:00', '2026-09-09 00:00', '2026-09-09 01:00']
```

**The daily path did not move.** One closed window in the past was fetched on
the branch and again with the branch stashed. Same rows, same digest.

```
branch          rows: 127  sha256: 25084443a18fcb7cacec3372fa0c4c3bb7070ac988391711e6afdbd80f1a373d
origin/current  rows: 127  sha256: 25084443a18fcb7cacec3372fa0c4c3bb7070ac988391711e6afdbd80f1a373d
```

**That digest can move.** The same window read at the weekly interval answers a
different count and a different digest, so the match above is a live reading and
not a check that cannot fail.

```
1w over the same window   rows: 26   sha256: 6b3187149adeb07a9b606a05e21a71180654de18d1a250925ad4121b5aad948c
```

## Error six — a window too short to read still cast a vote

### The vote on a partial window

A timeframe holding too few candles voted anyway. Twenty-five hourly candles
produced a direction, and seven of the twelve voters had abstained for want of
history.

```
one-day hourly window candles: 25
floor to vote: 30
voters: 12 abstained: 7
abstainers: ['macd', 'stochastic_rsi', 'ichimoku', 'volume', 'slingshot', 'adx', 'zscore']
consensus: SignalDirection.BULLISH net +0.5470 confidence 0.1164
```

### Reproducing the partial vote

One pair was read over a one-day hourly window and passed to the voting engine
directly. The window is a real venue answer, not a fixture.

### Why the scan never counted

The scan asked only whether candles came back. It never asked whether there were
enough of them, so a partial window reached the voters and a minority of them
decided the direction.

### The floor, and the report

The scan reports a short history instead of voting on it. The floor is the
thirty candles the gate scan already requires; no second number is introduced.

`src/trading/ata_spm.py` — the floor, and the report

```python
MIN_CANDLES_TO_VOTE = ata_gate_scan.MIN_CANDLES_FOR_TA

if len(candles) < MIN_CANDLES_TO_VOTE:
    found.short.append(symbol)
    cost.take(clock() - started)
    continue
```

### The short timeframe, after the floor

A one-day hourly window is reported and not voted. The other three timeframes
vote as before, in the same run.

```
 1h votes=0 unread=0 short=7 ['EUR/USD', 'USD/JPY', 'GBP/USD', 'USD/CHF', 'AUD/USD', 'NZD/USD', 'USD/CAD']
 1d votes=7 unread=0 short=0 []
 1w votes=7 unread=0 short=0 []
 1M votes=7 unread=0 short=0 []
```

The line the zone draws carries the count and the floor, under the operator's
own words for each timeframe.

```
Phase 1 Evaluate 1hr:   0 vote(s), 0 without candles, 7 under 30 candles
Phase 1 Evaluate 1d:    7 vote(s), 0 without candles, 0 under 30 candles
Phase 1 Evaluate 1wk:   7 vote(s), 0 without candles, 0 under 30 candles
Phase 1 Evaluate 1mnth: 7 vote(s), 0 without candles, 0 under 30 candles
```

**Both readings came from one instrument in one run.** It printed seven and it
printed zero, so a zero from it means the window was long enough.

## A non-daily run produced a call

The full scan called a reversal on the hourly timeframe, and phase eight now has
four timeframes to compare instead of one.

```
call: NZD/USD 1hr bearish net -1.0447 confidence 10%
pull: NZD/USD 1h bars 286
agreement: Timeframes: 1hr bearish · 1d bearish · 1wk bullish · 1mnth bearish.
           Contradicted on 1wk.
```

The contradiction row is the part that could not exist yesterday. One timeframe
cannot disagree with itself.

## What is not in this unit

**Crypto keeps two of its four timeframes.** The crypto universe scan holds
daily and weekly candles, so the five-minute and hourly boxes still report as
unserved on a crypto sector. That row of the rotation is a separate unit.

`src/trading/ata_asset_maps.py` — the crypto row, unchanged

```python
VENUE_EXCHANGE: (RA_TIMEFRAME, "1w"),
```

**Metals still lists no venue.** The four spot pairs carry no venue and are
reported, not scanned. That is unchanged by this unit.

**Seven pairs on four timeframes is twenty-eight requests per scan, and the
scan runs on the drawing thread.** The thread is its own arc and is not touched
here.

## What the operator sees differently

Scan Now on a FOREX sector now fills four timeframe rows instead of one, and a
post can carry a reversal called on the hour with the daily, weekly and monthly
votes beside it.

## Verdicts

```
coding_archetype  passed=True   exit 0   four files
ta_archetype      passed=True   exit 0   four files
gui_archetype     passed=True   exit 0   four files
local_ci black    PASSED        exit 0
local_ci flake8   PASSED        exit 0
known_good        exit 0        known_bad exit 1
```

Back to [the Market Inspector page](../../docs/manual/08-tabs/market-inspector.md).
