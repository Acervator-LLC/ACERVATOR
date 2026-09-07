# RA-StoneTablets: the portfolios in code, real prices on disk

The archive's thirty-five portfolios and sixty-three symbols are now a module
under `src/`. Their daily price history is fetched from two public endpoints and
written to a root of its own. One crypto symbol and one non-crypto symbol were
imported end to end and read back off disk. Nothing was carried out of the
archive except the definitions.

`~/.acervator/settings.json` hashed the same before and after:

```
before  f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
after   f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
```

No authenticated call and no credential. Both endpoints are public and were read
through `safe_urlopen`, which refuses any scheme but http and https.

## The definitions came out of the archive, nothing else did

The archive was extracted to a throwaway directory outside the repository. Its
three module-level tables were read with `ast` and evaluated on their own, with
no other line of the module running.

```
portfolios ......................... 35
symbols carrying price anchors ..... 63
symbols named by a portfolio ....... 63
symbols with no anchor row .......... 0
periods .... 2020, 2021, 2022, Apr23-Apr24, Apr24-Apr25, Apr25-Apr26
```

Those two counts match the audit of 7 September. Thirteen of the sixty-three are
crypto and fifty are not, which is what decides the source each symbol is
fetched from.

## Reproduce

One portfolio was loaded from the module and its symbols routed, then one year
was built for a symbol on each side of that split, in one process.

```
PORTFOLIO: DIGITAL_GOLD ('BTC', 'ETH', 'GLD', 'SLV') source= RAIntSimBat_standalone
WEIGHTS:   {'BTC': 0.25, 'ETH': 0.25, 'GLD': 0.25, 'SLV': 0.25}
ROUTING:   {'BTC': 'crypto', 'ETH': 'crypto', 'GLD': 'non-crypto', 'SLV': 'non-crypto'}
RA ROOT:   ~/.acervator_ra_tablets
```

## The store reached in the running program

`pdb` broke at the line that writes a tablet and read the live frame. The break
fired twice, once per source.

```
ra_fetcher.py(437)_store()
-> path = write_tablet(tablet, root=self._root)

('CoinbaseAdapter', '<absent>')
('coinbase', '2026-09-07T21:55:25+00:00', 365)
[1609459200000, 28990.08, 29688.88, 28700.0, 29412.84, 22211.25251806]

('YahooChartAdapter', 'yahoo_chart_v8_ONE_DAY_SPLIT_ADJUSTED')
('yahoo_chart_v8_ONE_DAY_SPLIT_ADJUSTED', '2026-09-07T21:55:27+00:00', 252)
[1609718400000.0, 181.97000122070312, 182.39999389648438, 180.9600067138672,
 182.3300018310547, 14331400.0]
```

Three defects are visible in those eight lines. A fourth came out of running the
same build twice.

## Defect 1 — the crypto tablet recorded no provenance

**The error.** The stored source read `coinbase`. That is an exchange id, not a
statement of where a number came from. This is the defect the archive audit
names: a figure with nothing behind it.

**The cause.** `_store` read the source with a default:

```python
            source=str(getattr(self._adapter, "SOURCE", self._adapter.exchange_id)),
```

`CoinbaseAdapter` is the fleet's own adapter and carries no such name. It
delegates its fetching to a connector, and the connector is what knows the
endpoint. The default swallowed the miss and wrote the exchange id instead.

**The correction.** The builder now takes the source at construction and refuses
to exist without one. The silent default is gone.

```python
        resolved = source or str(getattr(adapter, "SOURCE", ""))
        if not resolved:
            raise ValueError(
                f"{type(adapter).__name__} carries no SOURCE; pass source= naming "
                f"the endpoint the candles come from. {adapter.exchange_id!r} is "
                f"an exchange id, not provenance."
            )
```

**The rerun.** The old call site, unchanged, now raises rather than writing a
tablet with no provenance:

```
ValueError: CoinbaseAdapter carries no SOURCE; pass source= naming the endpoint
the candles come from. 'coinbase' is an exchange id, not provenance.
```

With the source supplied, the same break reads:

```
('CoinbaseAdapter', 'coinbase_exchange_candles_ONE_DAY')
('coinbase_exchange_candles_ONE_DAY', '2026-09-07T22:05:38+00:00', 365)
```

## Defect 2 — the non-crypto timestamp was a different type

**The error.** The Coinbase row carries `1609459200000` and the Yahoo row
carries `1609718400000.0`. Two tablets that a single tape will read were storing
the same field as two types.

**The cause.** The row builder cast the timestamp along with the prices.

```python
            rows.append([float(ts_ms), *(float(v) for v in values), float(volume)])
```

**The correction.** The timestamp stays an integer, matching what the fleet's
own adapter already writes.

**The rerun.** `[1609718400000, 181.97000122070312, ...]`.

## Defect 3 — a partly served year recorded nothing

**The error.** A request for the whole of 2026 for one symbol came back with 36
days and no record of the rest. Rows had arrived, so the run reported success,
and a reader of that tablet could not tell that seven months were never served.

**The cause.** A gap was recorded only when a range returned zero rows.

**The correction.** The served span is now compared against the requested one,
and the days outside it are recorded as gaps in their own right.

```python
    if since_ms < first:
        out.append((since_ms, first - DAY_MS, f"no rows before {_iso_day(first)}"))
    if last < until_ms:
        out.append((last + DAY_MS, until_ms, f"no rows after {_iso_day(last)}"))
```

**The rerun.** The same build now records both ends, and a symbol the source
does not carry at all still records the whole year.

```
GLD  2020 [2020-01-01..2020-01-01] no rows before 2020-01-02
COIN 2020 [2020-01-01..2020-12-31] HTTPError: HTTP Error 400: Bad Request
CCIV 2022 [2022-01-01..2022-12-31] HTTPError: HTTP Error 404: Not Found
BBBY 2026 [2026-01-01..2026-07-16] no rows before 2026-07-17
BBBY 2026 [2026-09-05..2026-09-07] no rows after 2026-09-04
```

Not one of those five wrote a candle. `COIN` listed in April 2021, so 2020 is
before its first trade and the endpoint answers 400. `CCIV` merged away in 2021
and the endpoint answers 404. The `GLD` row is New Year's Day and the second
`BBBY` row is a weekend plus Labor Day.

## Defect 4 — a rerun restamped the fetch time without fetching

**The error.** Running the same build a second time reported no range to
request, then rewrote the tablet anyway. The stored fetch time moved to the
second run, for candles the second run never fetched. That is the same class as
defect 1: the tablet stating something about its own numbers that is not true.

**The cause.** The write ran unconditionally once any row was held.

**The correction.** The tablet is written only when the merged rows differ from
the rows already on disk.

```python
        build.tablet_file = (
            path.name if merged == held else self._store(asset_u, year, candles).name
        )
```

**The rerun.** A build at 22:09:41 left both fetch times where they were:

```
BTC 2020 366 rows  fetched_at 2026-09-07T22:05:49+00:00
GLD 2020 253 rows  fetched_at 2026-09-07T22:05:50+00:00
```

## The two sources, and why these two

**Crypto: the Coinbase Exchange public candle endpoint.** It needs no key, it
serves daily candles, and it reaches back to each product's listing. It is read
through the adapter the fleet already uses, so the crypto path gains no second
implementation.

**Non-crypto: the Yahoo Finance chart endpoint.** It needs no key and no paid
tier, it serves daily open, high, low, close and volume for every non-crypto
class the thirty-five portfolios name — shares, index funds, bond funds,
property and sector funds — and it reaches back further than 2020, which is the
earliest period the archive addresses. Its prices are adjusted for splits. The
archive's own module reached for this same host and never used it.

**Stooq was tried first and refused.** Four requests returned HTTP 200 whose
body was a JavaScript challenge page rather than the daily file:

```
STOOQ spy.us : http=200 lines=3  <!DOCTYPE html> ... This site requires JavaScript
STOOQ aapl.us: http=200 lines=3  <!DOCTYPE html> ... This site requires JavaScript
STOOQ bbby.us: http=200 lines=3  <!DOCTYPE html> ... This site requires JavaScript
STOOQ cciv.us: http=200 lines=3  <!DOCTYPE html> ... This site requires JavaScript
```

Alpha Vantage, Tiingo, Polygon, Finnhub and Marketstack were not tried. Each
requires an account key, which this unit may not hold.

## The tablets, read back off disk

```
BTC_1d_2020_coinbase.json
  rows        366
  first       2020-01-01T00:00:00+00:00
  last        2020-12-31T00:00:00+00:00
  source      coinbase_exchange_candles_ONE_DAY
  fetched_at  2026-09-07T22:05:49+00:00
  first row   [1577836800000, 7165.72, 7238.14, 7136.05, 7174.33, 3350.63004888]
  last  row   [1609372800000, 28897.42, 29321.9, 28000.0, 28990.08, 28813.88691084]

GLD_1d_2020_yahoo.json
  rows        253
  first       2020-01-02T00:00:00+00:00
  last        2020-12-31T00:00:00+00:00
  source      yahoo_chart_v8_ONE_DAY_SPLIT_ADJUSTED
  fetched_at  2026-09-07T22:05:50+00:00
  first row   [1577923200000, 143.86000061, 144.21000671, 143.39999390, 143.94999695, 7733800.0]
  last  row   [1609372800000, 178.07000732, 178.39999390, 177.32000732, 178.36000061, 7540800.0]
```

366 rows is every day of a leap year. 253 rows is the number of days the New
York market opened in 2020.

## The stored prices against the source

Each stored row was compared against a fresh single-day read of the endpoint it
came from.

```
BTC 2020-01-01 stored : [1577836800000, 7165.72, 7238.14, 7136.05, 7174.33, 3350.63004888]
BTC 2020-01-01 source : [1577836800,    7136.05, 7238.14, 7165.72, 7174.33, 3350.63004888]
                         time_s         low      high     open     close    volume
  open True   high True   low True   close True

GLD 2020-01-02 stored : [1577923200000, 143.86000061, 144.21000671, 143.39999390, 143.94999695, 7733800.0]
GLD 2020-01-02 source : ts=1577975400   o=143.86000061 h=144.21000671 l=143.39999390 c=143.94999695 v=7733800
  open True   high True   low True   close True
```

The two venues send their fields in different orders, so the comparison is what
proves the mapping. Both timestamps are moved back to the UTC midnight of their
own day, which is why the market-open stamp of 1577975400 is stored as
1577923200000.

## A second run fetches nothing it already holds

Running the same build again reports no range to request for the tablet that is
complete, and re-asks only for the day the source has never served.

```
BUILD BTC 2020 : candles_written=366  ranges_requested=[]
BUILD GLD 2020 : candles_written=253  ranges_requested=[(1577836800000, 1577836800000)]
```

## The live tablet tree was not touched

Listed by name and size before any work started and again after every run above:

```
before  407 files  385,371,453 bytes  20294dfd7baaee0f859d0f95db8e3ddcc989f28b78f403704b5406214f72f152
after   407 files  385,371,453 bytes  20294dfd7baaee0f859d0f95db8e3ddcc989f28b78f403704b5406214f72f152
```

Read a second way, including each file's modification time, the digest was
`be68d354cf091659877279e85ca9f0a0b6379b8efefe6b5f8aa3c11c6de33872` before and
after the build run. Nothing under that tree was opened for writing. The new
tablets are in a separate root:

```
~/.acervator_ra_tablets/
  BBBY_1d_2026_yahoo.json    3,797
  BTC_1d_2020_coinbase.json 23,512
  GLD_1d_2020_yahoo.json    25,261
  GAPS.json                  1,643
  MANIFEST.json              1,543
  _scratch/
```

## Edits

`src/simulator/portfolios.py` — new. `PORTFOLIOS` holds the thirty-five
portfolios, each with its symbols, its archive description and its source.
`Portfolio.weights` divides one share equally, because the archive committed the
same capital to every symbol it ran. `SYMBOLS` is the sixty-three, `PERIODS` is
the six archive windows with their dates, and `is_crypto` decides which source a
symbol is fetched from.

`src/trading/stone_tablets/ra_paths.py` — new. `RA_STONE_TABLETS_DIR` is the one
definition of the RA root, derived from `Path.home()`. It is a sibling of the
live runtime tree, not a subdirectory of it.

`src/trading/stone_tablets/ra_fetcher.py` — new. `YahooChartAdapter` is a third
subclass of the existing adapter base. `CoinbasePublicCandles` supplies the
candle surface the fleet's own Coinbase adapter calls, without a credential.
`RaTabletBuilder.build_year` fetches only what the stored tablet lacks, writes
through the existing tablet storage, and records every unserved period as a
`TabletGap`.

`tests/conftest.py` — the live-tree guard watched two runtime roots and this
unit created a third, so a test writing to it would have gone unreported.
`_live_roots` now returns three.

`docs/manual/08-tabs/simulator.md` — a new section under the existing ones.

## No manual sentence was deleted or reworded

```
git diff --numstat docs/manual/08-tabs/simulator.md   ->   82  0
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
coding_archetype  src/simulator/portfolios.py                passed  exit 0
coding_archetype  src/trading/stone_tablets/ra_paths.py      passed  exit 0
coding_archetype  src/trading/stone_tablets/ra_fetcher.py    passed  exit 0
coding_archetype  tests/conftest.py                          passed  exit 0
ta_archetype      src/simulator/portfolios.py                passed  exit 0
ta_archetype      src/trading/stone_tablets/ra_fetcher.py    passed  exit 0
docs_archetype    docs/manual/08-tabs/simulator.md           passed  exit 0
```

## Tests run

The one canon file that names the changed symbol, run serially, no `-n`:

```
tests/test_live_tree_guard.py     53 passed, exit 0
```

That file already carries the two-sided proof for this change.
`test_created_file_fails_the_session` drives the guard over an injected root and
asserts it raises on a created file, so a guard that stopped reporting would
fail there. `test_live_roots_is_injectable` patches the root list rather than
pinning its contents, which is why a third root does not break it.

## What is not done

No bot logic runs over these tablets, no timeframe comparison exists, and no
screen shows any of it. Sixty-one of the sixty-three symbols have no tablet yet.
Those are later units.

One reading to carry into the next unit: the ticker `BBBY` now resolves to a
company first traded on 16 July 2026, not to the company the archive meant. The
tablet and its gap rows state exactly that, and no candle was invented to cover
the difference, but a symbol whose name has been reused is not the same
instrument the archive ran.

## What the operator sees differently

Nothing on screen yet. On disk there is now a second tablet tree holding real,
sourced daily prices for the Portfolio Battery, and the thirty-five portfolios
he asked to keep are in the code rather than in a zip on his desktop.
