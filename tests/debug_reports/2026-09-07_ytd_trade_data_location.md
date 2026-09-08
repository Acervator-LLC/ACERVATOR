# The YTD trade data location

Issue #117. The location, its format and its writer. No validation, no button.

## What one file is

One file holds one exchange, one symbol and one year. That grain matches the
RA-StoneTablet files, which are one asset, timeframe, year and exchange each, so
validation opens one trade file and one tablet for the same asset and year and
joins them without scanning across files.

The exchange is a field inside the file, not only a part of its name. A file
that is moved or renamed still says which venue its trades came from.

```
BTC-USD_2026_coinbase.json      one exchange, one symbol, one year
MANIFEST.json                   one row per file, with counts and date span
GAPS.json                       every period no row covers
```

## What it holds

```
schema_version      1
exchange_id         the venue, inside the file
symbol              BASE/QUOTE
year                the UTC year the rows fall in
imported_at         when the rows last changed
trade_count         rows held
first_ts_ms         oldest row
last_ts_ms          newest row
checksum_sha256     over the rows alone
sources             one entry per export that contributed rows
trades              id, ts_ms, side, amount, price, cost, fee, fee_currency
```

`amount` and `cost` are magnitudes. `side` carries the direction, so a sell is
stored positive with `side` reading SELL.

## The root, and how it is redirected

`src.exchange.ytd_trade_store.get_ytd_root` resolves an explicit argument first,
then `ACERVATOR_YTD_TRADES_ROOT`, then `src.core.log_paths.get_exchange_history_dir`.
The environment key follows the pattern `tests/conftest.py` uses in
`_redirect_writable_roots` for the telemetry, settings and reservation roots.
Every run below set that key at a throwaway directory.

## The columns the import requires

Nine columns, read from a transactions CSV export. The header is found by
scanning the first 20 rows, because the export carries a preamble above it.

```
ID                       -> id, and the append key
Timestamp                -> ts_ms          'YYYY-MM-DD HH:MM:SS UTC' or ISO 8601
Transaction Type         -> side           buy and sell types only
Asset + Price Currency   -> symbol         'ASSET/CURRENCY'
Quantity Transacted      -> amount         sign checked, magnitude stored
Price at Transaction     -> price
Subtotal                 -> cost           magnitude
Fees and/or Spread       -> fee
Price Currency           -> fee_currency
```

`Notes`, `Sender Address` and `Recipient Address` are never carried in.

## Reproduce

Two drivers, both outside the repository, both pointing the root at a throwaway
directory. One builds CSV rows by hand; one reads the operator's own export.

```
python -X dev -X faulthandler <driver>
python -X dev -m pdb -c "b src/exchange/ytd_csv_import.py:<line>" -c c ... <driver>
```

## Error 1 — a sell quantity is negative in the export

The first run against the operator's export stopped on the first data row.

```
File "src/exchange/ytd_csv_import.py", line 272, in _trade_of
    raise YtdImportRefused(message)
YtdImportRefused: row 5: column 'Quantity Transacted' is not above zero
```

**Cause.** A breakpoint at that frame read the raw cell with its digits masked:
`-9.9`, on an `Advanced Trade Sell`. The export encodes direction twice, in the
transaction type and in the sign of the quantity.

Counted across the whole export, the convention holds without exception:

```
Advanced Trade Buy    3221   quantity positive
Advanced Trade Sell   2533   quantity negative
Buy                      8   quantity positive
Sell                     4   quantity negative
```

**Correction.** `sign_matches_side` refuses a row whose sign disagrees with its
type, and the magnitude is stored with the side beside it. This matches the live
path, where a trade amount is a positive number and the side is a separate
field.

**Rerun.** All 5,766 trade rows accepted. The check is not inert: the
constructed fixture originally wrote its sells positive, and the same check
refused it — `row 6: column 'Quantity Transacted' sign disagrees with column
'Transaction Type' side SELL`. The fixture was corrected to the real convention.

## Error 2 — the minus sign precedes the currency mark

```
File "src/exchange/ytd_csv_import.py", line 153, in parse_money
    return float(cleaned)
ValueError: could not convert string to float: '-$1.46731'
YtdImportRefused: row 5: column 'Subtotal' is not a number
```

**Cause.** `parse_money` stripped the currency mark from the front, so a value
written as minus-then-mark kept both characters.

**Correction.** The parser now strips signs and currency marks from the front in
any order, remembering the sign, and applies it to the parsed number.

**Rerun.** No refusal. Both orders parse.

## Rows in, file out

Eight constructed rows: five trades across two symbols and two years, plus one
reward income, one deposit and one withdrawal.

```
rows_read       8
rows_kept       5
dropped_by_type {'Reward Income': 1, 'Deposit': 1, 'Withdrawal': 1}
symbols         ['BTC/USD', 'ETH/USD']
files_written   4
```

The file that came out, in full:

```json
{
  "schema_version": 1,
  "exchange_id": "coinbase",
  "symbol": "BTC/USD",
  "year": 2024,
  "imported_at": "2026-09-08T02:15:46+00:00",
  "trade_count": 2,
  "first_ts_ms": 1709546400000,
  "last_ts_ms": 1726943400000,
  "checksum_sha256": "bc0cf5a889ab073321ec4271ea04d921fc6990e09dfa91618a7f4194da736f64",
  "sources": [
    {
      "file": "export_one.csv",
      "sha256": "983d5bad6e335df4244dadb5ae843f3e8db30af0e6e8ac0800c4bcf21d00f58a",
      "imported_at": "2026-09-08T02:15:46+00:00",
      "rows_added": 2
    }
  ],
  "trades": [
    {
      "id": "c-001",
      "ts_ms": 1709546400000,
      "side": "BUY",
      "amount": 0.5,
      "price": 40000.0,
      "cost": 20000.0,
      "fee": 50.0,
      "fee_currency": "USD"
    },
    {
      "id": "c-002",
      "ts_ms": 1726943400000,
      "side": "SELL",
      "amount": 0.25,
      "price": 44000.0,
      "cost": 11000.0,
      "fee": 27.5,
      "fee_currency": "USD"
    }
  ]
}
```

The words Notes, Sender Address and Recipient Address appear nowhere in it.

## Read back, row for row

Read through the Simulator's reader and compared field by field against what
went into the CSV.

```
trade rows in the CSV       5
rows read back and matching 5
rows that went in unread    []
mismatched                  []
```

## A period with no rows, recorded as a gap

The constructed export covers 2024 to 2026 and holds nothing in 2025.

```
BTC/USD 2025: export_one.csv carries no BTC/USD trade in 2025
ETH/USD 2025: export_one.csv carries no ETH/USD trade in 2025
2025 files on disk: []
total gaps recorded: 8
```

The other six gaps are the edges — the covered days before a symbol's first
trade and after its last, inside each year. No row is invented anywhere.

## Append

A second import of the same export changes nothing.

```
trades_added    0
files_written   []
files_unchanged 4 of 4
byte-identical  4 of 4
```

A breakpoint inside the merge shows it refusing the duplicates in the frame:

```
('BTC/USD', 2024, ['c-001', 'c-002'], ['c-001', 'c-002'])   held, incoming
(0, ['c-001', 'c-002'])                                     added, merged
```

A second import carrying one repeat and two new rows adds only the two.

```
rows_kept in second export 3
trades_added               2
BTC-USD_2026: 1 -> 2       ETH-USD_2026: 1 -> 2
BTC-USD_2024: 2 -> 2       ETH-USD_2024: 1 -> 1   both byte-identical
c-003 present exactly once
every original id still on disk: True
```

## Refusing a file with a missing column

```
YtdImportRefused: no header in the first 20 rows carries every required column.
Closest is row 4, missing ['Price at Transaction']. Required: ['ID',
'Timestamp', 'Transaction Type', 'Asset', 'Quantity Transacted', 'Price
Currency', 'Price at Transaction', 'Subtotal', 'Fees and/or Spread'].
```

## The reader refusing a send

`YtdTradeSource` answers six names and raises `SendRefused` for every other.

```
place_order        SendRefused
create_market_buy  SendRefused
cancel_order       SendRefused
withdraw           SendRefused
write_trade_file   SendRefused
save               SendRefused
root, entries, entry_for, symbols, trades, gaps   all answer
```

`SendRefused` is the same class the tablet reader raises, imported rather than
restated. A call for information is not a send, so nothing here forbids the
Simulator fetching its own trade data.

## The operator's own export

Read into a throwaway directory. No credential, no venue call. No row, balance
or order id is reproduced here.

```
rows_read       5798
rows_kept       5766
dropped_by_type {'Reward Income': 16, 'Deposit': 15, 'Withdrawal': 1}
symbols         39
files_written   39
sides           BUY 3229, SELL 2537
years           [2026]
date range      2026-04-12 to 2026-09-07
gaps recorded   76
sum trade_count 5766
every entry names its exchange        True
every file names its exchange inside  True
```

Re-importing the same export a second time:

```
trades_added    0
files_written   0
files_unchanged 39
byte-identical  39 of 39
```

## The operator's tree

```
~/.acervator/settings.json before  2b1946b9560593d7e437805a62e9770a5aed28af0827251bb84c0125862abc7e
~/.acervator/settings.json after   2b1946b9560593d7e437805a62e9770a5aed28af0827251bb84c0125862abc7e
~/.acervator_logs/exchange_history contents  empty, before and after
~/.acervator_ra_tablets entries              414, before and after
```

The log tree file count moved from 4073 to 4074. The new file is the running
platform's daily profit-and-loss file for the next UTC day. Every file with a
recent timestamp is a live writer — the heartbeat, the gate log, the voting log,
the console log and the session signals. None of them is written by anything in
this unit, and the one directory this unit's writer targets is still empty.

## Error 3 — two manual pages cited a deleted test

Found while running the tests that name the changed symbols. Both fail the same
way on the branch this unit was cut from, so this unit did not cause them.

```
FAILED test_doc_page_names_no_missing_path[docs/manual/10-live-trade-history.md]
FAILED test_doc_page_names_no_missing_path[docs/manual/FIGURES.md]
    docs/manual/FIGURES.md:178: tests/test_vwap_band_scales_to_price.py
```

**Cause.** Both pages quote a history walk whose whole point is that this path
was deleted. The checker excuses a block that carries an absence marker, and a
Markdown block ends at a blank line, so the marker in the paragraph above never
reaches the listing below it.

**Correction.** One annotation line added inside each listing, in the form the
listing already uses, reading `deleted; not in the tree`. No existing line is
changed: one line added to each page, nothing removed.

**Rerun.** 75 passed, exit 0. Red before, green after.

## Archetypes

```
src/exchange/ytd_trade_store.py    coding passed   ta passed
src/exchange/ytd_csv_import.py     coding passed   ta passed
src/simulator/ytd_trade_source.py  coding passed   ta passed
src/core/log_paths.py              coding passed   ta passed
docs/manual/08-tabs/simulator.md   docs passed
docs/manual/08-tabs/history.md     docs passed
docs/manual/FIGURES.md             docs passed
docs/manual/10-live-trade-history.md  docs passed
```

Instrument controlled once this session: the coding archetype exits 0 on the
known-good fixture and 1 on the known-bad one.

## What is not done

Validation, the discovery of files on disk with its three branches, and the
Generate From YTD button. This unit builds the location, its format and its
writer only.
