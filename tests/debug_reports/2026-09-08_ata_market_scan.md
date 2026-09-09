# ATA-SMP scans a real market outside crypto

**Mode: Debug report.** Three program errors, each reproduced, diagnosed,
corrected and run again. The run drove Scan Now over FOREX and over metals.

Nothing was posted. No account and no credential was used. Every price read is
public market data. The platform ran while this page was written; nobody
started a second instance and nobody attached to the running one.

`~/.acervator/settings.json` hashed the same before and after:
`18D380C7134DADBB2ACBF5CBE5527EA177FE8B23CC77EB3FFF6334FB03FEEAC8`.

## What was measured first, and it is the whole problem

The sector reader answered an empty list for every asset class except crypto,
and said so in its own docstring. The seam built to inject another source had
no caller. A scan of stocks, FOREX or metals therefore read no assets at all.

`src/gui/main_tabs/market_inspector_surface.py` — the reader before this unit

```python
def sector_assets(sector: Any, asset_class: Any) -> list:
    if str(asset_class) != ata_spm.CLASS_CRYPTO:
        return []
```

## The class chosen, and why

**FOREX.** The item names its tiers by liquidity and enumerates the major tier
in full: seven pairs, each holding USD. The minor tier is defined as a cross of
two majors, which fixes its membership from the same seven currencies. Every
one of the 28 names was then read from the venue before the map was written.

**Metals is the class that reports an absence.** The item names four spot pairs
per troy ounce. The one configured non-crypto venue answers HTTP 404 for every
spelling of all four, measured in the same run that answered 28 FOREX tickers.

```
forex major     7 of 7 answered      283 daily rows each
forex minor    21 of 21 answered     283 daily rows each
metals spot     0 of 6 answered      HTTP 404, four names and two alternates
```

**Stocks and derivatives are not built.** GICS names eleven sectors, and the
company membership behind them is licensed by MSCI and S&P; no list of it sits
in this tree. Derivatives has no classification named yet. Both are recorded in
the map's own source table.

`src/trading/ata_asset_maps.py` — what each class's map was built from

```python
MAP_SOURCES: dict[str, str] = {
    CLASS_STOCKS: (
        "GICS names 11 sectors over 25 industry groups, 74 industries and 163 "
        "sub-industries. The company membership is licensed by MSCI and S&P "
        "and no list of it sits in this tree."
    ),
    CLASS_DERIVATIVES: "No classification is named for this class yet.",
}
```

## Error one — a listed pair answered no candles

### The empty answer

The venue answered 258 rows and the scan saw none. The debug channel carried
the reason.

```
DEBUG:acervator.ata_asset_maps:ata asset map: EURUSD=X sent a row that is not
a candle: row 19: open=1.1654603481292725 is outside
[low=1.1603620052337646, high=1.1652973890304565]
```

### Reproducing the empty answer

```
cd <repo>
PYTHONWARNINGS=error python -X dev -X faulthandler <scratch>/u407_venue_read_debug.py
```

The script builds the listing for one pair, fetches one daily range through the
adapter, and prints the row count beside what the reader answered.

```
listing : AssetListing(symbol='EUR/USD', quote='USD', venue='yahoo', ticker='EURUSD=X')
error   : None
rows    : 258
candles : []
```

### Why the reader answered none

`candles_from_raw` in `src/trading/indicators/types.py` refuses a row whose open
or close sits outside its own high and low, which is correct: that row is not a
candle. The reader called it once over the whole list, so one refused row
discarded the other 257.

A census over the seven major pairs measured how common the fault is. It is a
venue data fault, not a rounding artefact — the gaps run from one to fifteen
basis points.

```
EUR/USD 258 rows, 248 kept, 10 refused      NZD/USD 258 rows, 244 kept, 14 refused
USD/JPY 258 rows, 242 kept, 16 refused      USD/CAD 258 rows, 250 kept,  8 refused
GBP/USD 258 rows, 253 kept,  5 refused      TOTAL  1806 rows,          75 refused
USD/CHF 258 rows, 251 kept,  7 refused      refused share 4.2%
AUD/USD 258 rows, 243 kept, 15 refused
```

### The row-by-row conversion

Convert one row at a time, keep every row the candle contract accepts, and count
the refusals into the log. Nothing is clamped and no price is invented; a row the
venue sent that is not a candle is dropped and counted.

`src/trading/ata_asset_maps.py` — the corrected conversion

```python
def _candles_of(ticker: str, rows: Any) -> list:
    """Every row ``candles_from_raw`` accepts, one row at a time.

    A venue row whose open or close sits outside its own high and low is not
    a candle, and it is counted into ``VENUE_ROWS_REFUSED_LOG``.
    """
    kept: list = []
    refused: list = []
    for row in list(rows or []):
        try:
            kept.extend(candles_from_raw([row]))
        except (CandleDomainError, IndexError) as exc:
            refused.append(str(exc))
```

### The read, after the conversion

```
EUR/USD 1d: 248 candles via venue=yahoo ticker=EURUSD=X
            first=2025-09-10T00:00:00+00:00 last=2026-09-09T00:00:00+00:00
            last_close=1.1633317470550537
EUR/USD 1h: 0 candles via venue=yahoo
XAU/USD 1d: 0 candles via venue=<none>
```

The second line is the venue's own limit: the adapter serves the daily
timeframe and refuses the rest. The third is the metals absence.

## Error two — a scan that produced a call crashed the redraw

### The missing tally helper

The first run that produced a reversal call raised while the tab redrew its left
modules.

```
File "src/gui/main_tabs/market_inspector_surface.py", line 1430, in voting_panel
    summary=ivp.summary_text(rows),
AttributeError: module 'src.gui.main_tabs.indicator_panel_surface'
has no attribute 'summary_text'
```

### Reproducing the redraw crash

```
cd <repo>
PYTHONWARNINGS=error python -X dev -X faulthandler <scratch>/u407_tab_driver.py
```

The driver builds the real tab, names a FOREX sector on its board, and calls the
same worker method the Scan Now button starts.

### Why the helper is gone

`git log -S` names the commit. The trading-tab restyle deleted the tally helper
and its format string from the indicator panel surface, and the ATA-SMP voting
panel still called it. Nothing reached that line before, because no non-crypto
sector could answer an asset and no run produced a call.

```
e4d155dd feat(trading tab): nine widgets reach the Electron shell,
         and the voting panel is restyled
-SUMMARY_FORMAT = "▲ {bullish}  ▼ {bearish}  ─ {neutral}"
-def summary_text(multi_tf_summary: dict) -> str:
```

### The tally, restored

The tally now sits beside the panel that draws it, over the same three counts the
vote row publishes.

`src/gui/main_tabs/market_inspector_surface.py` — the tally, restored

```python
def panel_summary_text(rows: Any) -> str:
    """The vote tally beside a voting panel title, summed over its timeframes."""
    return PANEL_SUMMARY_FORMAT.format(
        bullish=sum(panel_tally(one, "bullish") for one in (rows or {}).values()),
        bearish=sum(panel_tally(one, "bearish") for one in (rows or {}).values()),
        neutral=sum(panel_tally(one, "neutral") for one in (rows or {}).values()),
    )
```

### The redraw, after the tally

The redraw reached the next fault in the same file, which is error three.

## Error three — a header built with a keyword the panel no longer takes

### The error

```
File "src/gui/main_tabs/market_inspector_surface.py", line 1345, in panel_header_row
    titles = ivp.column_titles(list(subset), include_aggregates=bool(aggregates))
TypeError: column_titles() got an unexpected keyword argument 'include_aggregates'
```

### The reproduction

The same driver and the same command as error two.

### The cause

The same commit narrowed that signature. The header builder still passed the
removed keyword, and the new function pads its titles to a fixed column count
rather than to the table it is drawn on, so the shorter second table would have
run past its own widths.

An audit read every attribute the surface asks of the indicator panel module and
checked each against the live module. Fifteen are read, none is now missing, and
the control shows the check can report one.

```
ivp attributes read: 15
missing: none
control - a name that cannot exist:
  hasattr(ivp, 'no_such_name_here') -> False
```

### The correction

The header takes the titles for its own columns and appends the aggregate names
the panel module still publishes.

`src/gui/main_tabs/market_inspector_surface.py` — the corrected header

```python
    widths = panel_column_widths(subset, aggregates)
    titles = ivp.column_titles(list(subset))[: 1 + len(list(subset))]
    if aggregates:
        titles = titles + list(ivp.AGGREGATE_TITLES)
```

### The rerun

The tab redraw completed with exit 0 and drew every zone.

```
run.phase : Phase 3 Pull: 1 sector(s), 1 call(s), 1 chart(s)
scan minor (forex): assets=21 votes=21 calls=1 unlisted=() unserved=('1h', '1w', '1M')
CALL NZD/CHF 1d bullish
PULL NZD/CHF 1d: bars=252 image_path=<scratch>/NZD-CHF_1d_1788912000000.png
ready to send: 7 post(s)
zone view position=1 of 1
zone view position=1 of 7
```

## The caller, on a pdb stack

The break sat on the line that reads the venue. The stack below is the tab's own
Scan Now worker, which both the Qt tab and the React tab run.

```
u407_tab_driver.py(30)main()
-> tab._compute_scan(settings.message_format, settings.max_supporting_indicators)
src/gui/market_inspector.py(1097)_compute_scan()
-> answered = self._ata_board.compute(
src/trading/ata_spm.py(1069)compute()
-> run(
src/trading/ata_spm.py(955)run()
-> scans = evaluate(sectors, asset_source, candle_source, engine, clock)
src/trading/ata_spm.py(636)evaluate()
-> _scan_timeframe(voter, assets, timeframe, candle_source, cost, ticker)
src/trading/ata_spm.py(658)_scan_timeframe()
-> candles = candles_for(candle_source, symbol, timeframe)
src/trading/ata_spm.py(552)candles_for()
-> return list(candle_source(symbol, timeframe) or [])
src/gui/market_inspector.py(1131)_scanned_candles()
-> return sector_candles(get_shared_inspector(), symbol, timeframe)
src/gui/main_tabs/market_inspector_surface.py(1951)sector_candles()
-> return ata_asset_maps.venue_candles(symbol, timeframe)
> src/trading/ata_asset_maps.py(213)venue_candles()
-> attempt = asyncio.run(
AssetListing(symbol='EUR/GBP', quote='GBP', venue='yahoo', ticker='EURGBP=X')
```

The bridge model reaches the same reader through its own press, and its stack
runs from that model's Scan Now down to the same line.

## The sector, its assets, and the venue on each

Seven rows for the major tier, twenty-one for the minor, each paired with the
venue and the ticker that venue spells it under.

```
EUR/USD  venue=yahoo ticker=EURUSD=X quote=USD listed=True serves_1d=True
USD/JPY  venue=yahoo ticker=USDJPY=X quote=JPY listed=True serves_1d=True
GBP/USD  venue=yahoo ticker=GBPUSD=X quote=USD listed=True serves_1d=True
USD/CHF  venue=yahoo ticker=USDCHF=X quote=CHF listed=True serves_1d=True
AUD/USD  venue=yahoo ticker=AUDUSD=X quote=USD listed=True serves_1d=True
NZD/USD  venue=yahoo ticker=NZDUSD=X quote=USD listed=True serves_1d=True
USD/CAD  venue=yahoo ticker=USDCAD=X quote=CAD listed=True serves_1d=True
```

The quote currency matters. The adapter refuses a series it is not quoted in, so
the row for the yen pair carries JPY and the row for the franc pair carries CHF.

## The run that produced a call

Twenty-one pairs voted on the daily timeframe. One carried a reversal: the
consensus and the Bollinger voter named the same direction, with the price at
the lower band.

```
NZD/CHF  bullish  net=+0.9582  conf=0.0879  band=0.0454  band_dir=bullish  reversal=True
```

Phase three pulled that chart, wrote four confirming sentences and rendered the
picture. Phase four filled the bucket with one post per push target.

```
Bollinger Bands: band position 0.0454. Votes bullish at 86% confidence.
Stochastic RSI: %K at 10.70. Votes bullish at 80% confidence.
Ichimoku Cloud: price above the cloud. Votes bullish at 70% confidence.
Supertrend: +0.652% from the Supertrend line. Votes bullish at 23% confidence.
```

A run over the major tier on the same day produced seven votes and no call. A
market that scans clean produces no artefact, which is the item's own rule.

## The sector no venue lists

The metals sector reads its four names, finds no venue for any of them, and
reports that. It fetches nothing.

```
scan spot (metals): assets=0 votes=0 calls=0
unlisted=('XAU/USD', 'XAG/USD', 'XPT/USD', 'XPD/USD')
unserved=()
Waiting on: No configured venue lists XAU/USD, XAG/USD, XPT/USD, XPD/USD.
```

An unserved timeframe is reported the same way and separately, so a venue gap
never reads as a timeframe that voted nothing.

```
Phase 1 Evaluate unserved: No venue serves 1hr, 1wk, 1mnth.
```

## The crypto path

The crypto reader still reads the shipped tag file, and its symbols still chart
off the universe scan. The map decides the source, so a crypto name never
reaches the outside venue.

```
sector_assets('l1', 'crypto') -> 18 row(s)
  ADA  venue=exchange ticker=ADA listed=True serves_1d=True serves_5m=False
sector_candles BTC 1d -> ['candle-a', 'candle-b']
listing_of('BTC')     -> None
crypto scan: assets=18 unlisted=() unserved=('5m', '1h') timeframes=['1d', '1w']
```

The two fast timeframes now report as unserved. The universe scan keeps daily and
weekly candles only, so those two never had candles to read.

## What is not done

**Stocks and derivatives answer no assets.** Both are recorded in the map source
table with what each needs.

**Three of four non-crypto timeframes have no venue.** The adapter serves the
daily timeframe alone, so the hourly, weekly and monthly boxes report as
unserved on every non-crypto sector.

**The exotic tier is empty.** The item defines it and names no pair, and no pair
was invented.

**The bridge press reads the venue on the thread that calls it.** The tab's own
press already runs on a worker thread; the bridge handler does not.

## Figures

This report carries no figure. The chart the run rendered is produced output and
is not kept in the repository. It measured 1200 by 420 pixels and 149,167 bytes
under the scratch post root the run redirected to. The operator's own post
folder holds no name from any of the maps this unit added, checked after the
run.
