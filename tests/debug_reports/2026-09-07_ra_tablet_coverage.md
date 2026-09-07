# RA-StoneTablets: every portfolio symbol, every archive year

The import is complete. Sixty of the sixty-three Portfolio Battery symbols have
real daily prices on disk, over 2020 to 2026, in 411 tablets holding 105,336
candles from two public endpoints. Three symbols returned nothing and are
recorded as gaps. No price was invented.

`~/.acervator/settings.json` hashed the same before and after:

```
before  f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
after   f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
```

No credential and no authenticated call. Both endpoints are public and were read
through `safe_urlopen`, which refuses any scheme but http and https.

## The years, and why every portfolio gets all of them

No portfolio in `src/simulator/portfolios.py` carries a period of its own. The
dataclass holds a name, its symbols, a description and its source, and nothing
else. `PERIODS` sits beside `PORTFOLIOS` as one module-level table of the six
archive windows, applied to the battery as a whole rather than per portfolio.

Nine descriptions name a year in prose — `China tech crash 2021`,
`Crypto collapse 2022`, `SPAC bubble burst 2021-2022`. Prose is not a field, and
reading a period out of a sentence would invent a mapping the archive does not
state.

**The widest span the definitions support was taken, and it is recorded
here:** every symbol over every calendar year the six periods touch. The first
period opens on 2020-01-01 and the last closes on 2026-04-01, which makes the
span 2020 to 2026 inclusive — seven years for all 63 symbols, 441 symbol-years
asked for.

```python
RA_YEARS = (2020, 2021, 2022, 2023, 2024, 2025, 2026)
```

## Reproduce

```
python -m src.trading.stone_tablets.ra_import import
python -m src.trading.stone_tablets.ra_import coverage
```

The import ran serially, one request at a time, from 15:29:07 to 15:49:20 —
20 minutes 13 seconds for 441 builds. Exit code 0.

## The store reached in the running program

`pdb` broke at the line that chooses the fallback source and read the live
frame. `BNB` is a coin Coinbase did not list until October 2025.

```
ra_import.py(112)import_symbols()
-> build = await made[route.fallback].build_year(route.symbol, year)

SymbolRoute(symbol='BNB', primary='coinbase', fallback='yahoo_crypto')
2021
('coinbase', 0, ['source returned no rows'])
'BNB-USD'
'RaCoinbaseAdapter'
```

The primary served nothing, the fallback is chosen, and the ticker it will ask
for is `BNB-USD`. Three defects came out of driving this path. A fourth was
found by reading the coverage function's own frame.

## Defect 1 — the coverage report read the live fleet's tree

**The error.** The import's own printed statement said sixty-three symbols were
asked for, none returned data, and the sources were
`coinbase_advanced_trade_candles_FIVE_MINUTE` and
`coinbase_advanced_trade_v3_candles`. Neither is an RA source. Those are the
live fleet's five-minute tablets.

**Reproduction.** `python -m src.trading.stone_tablets.ra_import coverage`.

**The cause.** `coverage(root=None)` passed `None` straight to `read_manifest`,
whose own default is the live tree:

```python
def read_manifest(root: Optional[Path] = None) -> list[TabletEntry]:
    r = root or STONE_TABLETS_DIR
```

`read_gaps` defaults to `RA_GAPS_PATH` and `RaTabletBuilder` defaults to
`get_ra_root()`, so three functions in one path had two different ideas of home.
Both trees hold a file called `MANIFEST.json`, which is why nothing complained.

**The correction.** The RA root is resolved before the read.

```python
    base = root or RA_STONE_TABLETS_DIR
    entries = read_manifest(base)
```

**The rerun.** `pdb` at the resolving line, with no root supplied:

```
ra_import.py(256)coverage()
-> base = root or RA_STONE_TABLETS_DIR
(Pdb) p root
None
(Pdb) n ; p base.name
'.acervator_ra_tablets'
```

The same break stepped two lines further reads 411 entries carrying only the two
RA sources. The live manifest holds 406 entries and assets such as `1INCH` and
`AAVE`, which no portfolio names:

```
read_manifest(None) -> 406 entries, assets ['00', '1INCH', '2Z', 'A8', 'AAVE', 'ABT']
read_manifest(RA)   -> 411 entries, assets ['AAPL', 'ADA', 'AGG', 'AMC', 'AMD', 'AMZN']
```

This is OCIR **C25** — two files sharing a basename, and the wrong one answering.

## Defect 2 — a permanent 404 cost four requests and fourteen seconds

**The error.** A coin Coinbase does not list was asked for four times, with two,
four and eight second waits between attempts.

```
coinbase fetch TRX/USD [..] attempt 1/4 failed: HTTP Error 404 — sleeping 2.0s before retry
coinbase fetch TRX/USD [..] attempt 2/4 failed: HTTP Error 404 — sleeping 4.0s before retry
coinbase fetch TRX/USD [..] attempt 3/4 failed: HTTP Error 404 — sleeping 8.0s before retry
coinbase fetch TRX/USD [..] attempt 4/4 failed: HTTP Error 404 — no attempts left
```

**Reproduction.** Build any year for `TRX`, `BNB` or `MATIC` before 2021.

**The cause.** `CoinbaseAdapter.fetch_chunk` passed `retry_any` to the retry
loop, and `retry_any` accepts every exception. A 404 names a product the venue
does not list, and it will never become anything else.

**The correction.** The predicate became an overridable method on the base
adapter, defaulting to exactly what it did before, so the live fleet's behaviour
does not move:

```python
    @staticmethod
    def is_retryable(exc: BaseException) -> bool:
        """True when a failed ``fetch_chunk`` is worth another attempt."""
        return retry_any(exc)
```

`RaCoinbaseAdapter` narrows it, because its connector raises `HTTPError` and a
status code says whether another attempt can help.

```python
RETRYABLE_HTTP_CODES: frozenset[int] = frozenset({408, 429, 500, 502, 503, 504})
```

**The rerun.** The same build, and the live adapter unchanged beside it:

```
coinbase fetch TRX/USD [..] attempt 1/4 failed: HTTP Error 404 — no attempts left
TRX + GLD, one year each, elapsed 6.7s   (was 35s)

                   404      429     URLError
ExchangeAdapter    True     True    True
CoinbaseAdapter    True     True    True
RaCoinbaseAdapter  False    True    True
```

The live path answers exactly as it did. Only the RA subclass refuses a
permanent status, and it still retries a rate limit.

## Defect 3 — the Yahoo adapter declared a retry budget it never used

**The error.** `YahooChartAdapter` set `retry_max = 3` and `retry_base_s = 2.0`
and its `fetch_chunk` caught every exception on the first attempt. A single rate
limit part way through a twenty-minute run would have been written down as a
permanent gap.

**Reproduction.** Any transient failure during a build. None occurred, which is
the point — the run would have recorded the gap and reported coverage as
complete.

**The cause.** The fetch was a bare `try` around one call, with the two declared
fields read by nothing.

**The correction.** The declared budget now drives `retry_async`, with the same
status predicate as the Coinbase side.

```python
        return await retry_async(
            op,
            attempts=self.retry_max,
            delay_for=exponential_delay(self.retry_base_s),
            is_retryable=is_transient_http,
            on_failure=_note,
        )
```

**The rerun.** Across 441 builds and roughly 900 requests, 69 attempts failed
and every one was permanent — 56 from Yahoo, 13 from Coinbase, all 400 or 404,
none retried, none slept.

```
yahoo   attempt 1/3   56    all "no attempts left"
coinbase attempt 1/4  13    all "no attempts left"
transient retries that slept  0
```

Neither endpoint refused or throttled the run.

## Defect 4 — a gap another source had already filled read as a gap

**The error.** A coin fetched from the fallback still carried the primary's
"served nothing" row in `GAPS.json`, so the same year read as both covered and
missing.

**Reproduction.** Build `BNB` for 2021; Coinbase records a gap and Yahoo writes
366 rows.

**The cause.** `_record_gaps` keys on asset, exchange, timeframe and year, so
two sources for one year keep two independent records. Nothing compared them.

**The correction.** A gap is marked superseded when another exchange holds rows
for the same asset and year, and the gap classes count only what still stands.

**The rerun.** Every gap now carries which it is:

```
  TRX    2020 coinbase  covered-elsewhere [2020-01-01..2020-12-31] HTTP Error 404: Not Found
  GLD    2020 yahoo     standing          [2020-01-01..2020-01-01] no rows before 2020-01-02
```

## The coverage answer

```
SYMBOLS
  asked for ......... 63
  returned data ..... 60
  symbol-years asked  441
  tablets ........... 411
  candles ........... 105,336

SOURCES
  coinbase_exchange_candles_ONE_DAY      71 tablets  2026-09-07T22:05:49..22:49:01
  yahoo_chart_v8_ONE_DAY_SPLIT_ADJUSTED 340 tablets  2026-09-07T22:05:50..22:49:20

  of those 340 Yahoo tablets, 321 are non-crypto and 19 are coins Coinbase
  did not list in that year, fetched as <SYMBOL>-USD

GAPS (524 recorded, 19 covered by the other source, 505 standing)
    333  market shut at the start of the window
    141  market shut at the end of the window
     21  endpoint 404 - ticker not found
      8  endpoint 400 - outside the ticker's traded range
      2  source returned no rows
```

The commonest reason is the market being shut. 474 of the 505 standing gaps are
a weekend or a public holiday at one end of a requested year, on a share.

Rows per symbol per year, with the first and last day of each, are in the full
statement the command prints. Two symbols show the shape:

```
  SPY
    2020    253 rows  2020-01-02..2020-12-31
    2021    252 rows  2021-01-04..2021-12-31
    2022    251 rows  2022-01-03..2022-12-30
    2023    250 rows  2023-01-03..2023-12-29
    2024    252 rows  2024-01-02..2024-12-31
    2025    250 rows  2025-01-02..2025-12-31
    2026    170 rows  2026-01-02..2026-09-04

  BTC
    2020    366 rows  2020-01-01..2020-12-31
    2021    365 rows  2021-01-01..2021-12-31
    2022    365 rows  2022-01-01..2022-12-31
    2023    365 rows  2023-01-01..2023-12-31
    2024    366 rows  2024-01-01..2024-12-31
    2025    365 rows  2025-01-01..2025-12-31
    2026    250 rows  2026-01-01..2026-09-07
```

## The trading-day count against a real calendar

A count is not coverage. The row counts were checked against the calendar the
market actually keeps, computed from `datetime` alone.

```
year  calendar  weekdays  share rows  distinct  weekdays not traded  coin rows
2020       366       262         253         4                    9        366
2021       365       261         252         2                    9        365
2022       365       260         251         1                    9        365
2023       365       260         250         1                   10        365
2024       366       262         252         1                   10        366
2025       365       261         250         1                   11        365
```

**Read the "distinct" column.** For 2022, 2023, 2024 and 2025 every single
share symbol reports the same row count — one distinct value across fifty
tickers fetched independently. That number is the trading-day count, not a
coincidence.

The right-hand column is weekdays minus rows, which is the number of weekdays
the exchange was shut. It lands on the published New York holiday schedule every
year: 9 in 2020, 2021 and 2022, 10 in 2023 and 2024, and 11 in 2025 — the ten
holidays plus the national day of mourning on 9 January 2025.

2020 and 2021 carry more than one distinct value because several symbols first
traded part way through those years, which the per-symbol spans show.

A coin year is the whole calendar year — 366 in the two leap years, 365
otherwise, one distinct value across the coins that traded the full year.

## The stored prices against the source

Each stored row was compared against a fresh single-day read of the endpoint it
came from. The two venues send their fields in different orders, so the
comparison is what proves the mapping.

```
SPY 2022-01-03 stored [1641168000000, 476.29998779, 477.85000610, 473.85000610, 477.70999146, 72668200.0]
SPY 2022-01-03 source [1641168000000, 476.29998779, 477.85000610, 473.85000610, 477.70999146, 72668200.0]
  open high low close all match

GLD 2020-01-02 stored [1577923200000, 143.86000061, 144.21000671, 143.39999390, 143.94999695, 7733800.0]
GLD 2020-01-02 source [1577923200000, 143.86000061, 144.21000671, 143.39999390, 143.94999695, 7733800.0]
  open high low close all match

ETH 2021-01-04 stored [1609718400000, 980.44, 1168.99, 886.33, 1042.38, 1103882.9026854]
ETH 2021-01-04 source [1609718400000, 980.44, 1168.99, 886.33, 1042.38, 1103882.9026854]
  open high low close all match

BNB 2021-01-04 stored [1609718400000, 41.19828033, 43.13212204, 38.14398193, 40.92635345, 807877171.0]
BNB 2021-01-04 source [1609718400000, 41.19828033, 43.13212204, 38.14398193, 40.92635345, 807877171.0]
  open high low close all match
```

`GLD`'s 2020 open of 143.86 on 2 January is the figure the previous unit
checked, and it reads the same now.

**A second check, against the other venue.** Reading the endpoint twice proves
storage, not price. Three coins stored from Coinbase were read again from Yahoo,
which is an independent market:

```
ETH 2021-01-04  coinbase close 1042.38   yahoo close 1040.23   difference 0.206%
BTC 2020-06-15  coinbase close 9432.53   yahoo close 9450.70   difference 0.192%
SOL 2023-03-10  coinbase close   18.23   yahoo close   18.24   difference 0.075%
```

Two venues that share no data path agree to within a fifth of one per cent.
These are market prices.

## The symbols that returned nothing, and why

Three of the sixty-three carry no candle in any year. Each records what the
endpoint answered.

```
CCIV  404 Not Found  every year   Churchill Capital VII merged into Lucid in 2021
EXPR  404 Not Found  every year   Express delisted after its 2024 bankruptcy
IPOF  404 Not Found  every year   Social Capital Hedosophia VI wound up in 2022
```

The 404 is the measurement. The sentence beside it names the company the archive
meant and is not a fetched fact.

Three more are short at one end, and two of those are the interesting kind.

```
BBBY   2020-2025  400 Bad Request, then a series starting 2026-07-17
MATIC  stops 2025-10-14, nothing in 2026 from either source
COIN   2020 absent, 2021 starts 2021-04-14
SOFI   2020 absent, 2021 starts 2021-01-04
```

**`BBBY` is a reused ticker.** The endpoint refuses every archive year and then
serves a company first traded on 16 July 2026. The tablet and its gap rows say
exactly that. It is not the company `MEME_HANGOVER` was built around, and no
candle was invented to cover the difference.

**`MATIC` is a renamed coin.** Coinbase serves it to 14 October 2025 and stops;
Yahoo's `MATIC-USD` serves nothing for 2026. Polygon renamed the token, so the
archive's ticker no longer addresses a traded instrument.

`COIN` and `SOFI` are first trades, not defects — both companies listed in 2021,
so 2020 does not exist to be fetched.

**One symbol records a venue's own history.** `XRP` shows the Coinbase
suspension in its spans, and the fallback covered the year Coinbase held none:

```
  XRP
    2021     19 rows  2021-01-01..2021-01-19  coinbase
    2022    365 rows  2022-01-01..2022-12-31  yahoo
    2023    172 rows  2023-07-13..2023-12-31  coinbase
```

Coinbase suspended XRP on 19 January 2021 and relisted it on 13 July 2023. The
tablets carry the gap where the venue had one, and real prices where another
venue did.

## The live tablet tree was not touched

Listed by name and size before any work started and again after every run above:

```
before  407 files  385,371,453 bytes  6e1d4a24e0992e074c85fe8bfcf7fcec852c68152d5d01e1bd57394dd369dc3a
during  407 files  385,371,453 bytes  6e1d4a24e0992e074c85fe8bfcf7fcec852c68152d5d01e1bd57394dd369dc3a
after   407 files  385,371,453 bytes  6e1d4a24e0992e074c85fe8bfcf7fcec852c68152d5d01e1bd57394dd369dc3a
```

Nothing under that tree, or under `~/.acervator_logs/`, was opened for writing.
The new tablets are in the separate root:

```
~/.acervator_ra_tablets/   413 files   9,829,596 bytes
  411 tablets, GAPS.json, MANIFEST.json
```

## Edits

`src/trading/stone_tablets/ra_import.py` — new. `RA_YEARS` derives the seven
years from `PERIODS`. `route_for` sends a symbol to its source and names the
fallback. `import_symbols` builds every symbol-year and re-asks the fallback for
a year the primary served nothing for. `coverage` reads the RA manifest and gap
file back, and `format_coverage` renders the statement. `main` runs the `import`
and `coverage` subcommands, each taking a symbol and year subset.

`src/trading/stone_tablets/ra_fetcher.py` — `is_transient_http` and
`RETRYABLE_HTTP_CODES` decide whether a status is worth another attempt.
`RaCoinbaseAdapter` narrows the base adapter's retry rule. `YahooChartAdapter`
takes a `ticker_suffix` and uses the retry budget it already declared.

`src/trading/stone_tablets/fetcher.py` — `ExchangeAdapter.is_retryable` is the
overridable seam, returning `retry_any` so the live fleet's behaviour is
unchanged.

`docs/manual/08-tabs/simulator.md` — a new section under the existing ones.

`tests/conftest.py` — unchanged. Its guard already watches all three roots.

## No manual sentence was deleted or reworded

```
git diff --numstat docs/manual/08-tabs/simulator.md   ->   93  0
git diff docs/manual/08-tabs/simulator.md | grep -c '^-[^-]'   ->   0
```

## Instruments, proved before use

```
coding_archetype  known_good.py           exit 0
coding_archetype  known_bad.py            exit 1
ta_archetype      known_good_ta001.py     exit 0
ta_archetype      known_bad_ta001.py      exit 1
docs_archetype    known_good.md           exit 0
docs_archetype    known_bad.md            exit 1
```

## Archetypes

```
coding_archetype  src/trading/stone_tablets/ra_import.py     passed  exit 0
coding_archetype  src/trading/stone_tablets/ra_fetcher.py    passed  exit 0
coding_archetype  src/trading/stone_tablets/fetcher.py       passed  exit 0
ta_archetype      src/trading/stone_tablets/ra_import.py     passed  exit 0
ta_archetype      src/trading/stone_tablets/ra_fetcher.py    passed  exit 0
docs_archetype    docs/manual/08-tabs/simulator.md           passed  exit 0
```

## Tests run

The canon files naming the changed symbols, run serially, no `-n`:

```
tests/test_core_retry_site_equivalence.py
tests/test_stone_tablets_fetcher.py        69 passed, exit 0
```

`test_core_retry_site_equivalence.py` is what pins the retry seam. It drives
`CoinbaseAdapter` through a connector that raises and asserts the attempt count,
so a predicate that stopped retrying a transient failure would fail there.

## What is not done

No bot logic runs over these tablets, no timeframe comparison exists, and no
screen shows any of it. The tablets are daily; the live registry's native
timeframe is five minutes, so a replay that reads both has a decision to make
that no code makes yet.

Three symbols — `CCIV`, `EXPR`, `IPOF` — have no public daily history under the
ticker the archive used. `BBBY` and `MATIC` have part of one. Five of the
thirty-five portfolios therefore run one symbol short of the archive:
`SPAC_BUST` loses two, `MEME_HANGOVER` loses two, and `EXTENDED`,
`RATE_SENSITIVE` and `CRYPTO` each lose part of one year.

## What the operator sees differently

Nothing on screen yet. On disk the Portfolio Battery now has real, sourced daily
prices for sixty of its sixty-three symbols across seven years, and a command
that says exactly what is there and what is missing.
