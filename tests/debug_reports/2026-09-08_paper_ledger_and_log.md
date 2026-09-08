# The Paper fleet ledger, the four figures and the Paper Trader log

Every reading below came from running the program against the venue's public
market feed. No test file was written.

`~/.acervator/settings.json` hashed the same before and after:

```
before  f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
after   f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
```

`~/.acervator_paper` does not exist on this machine. Every run below wrote to a
scratch root through `ACERVATOR_PAPER_ROOT`.

## The opening figures for a fleet of five $200 bots

`opening_ledger` was called on five `PaperBot` records, then `figures` was read
over five balances `opening_balance` opened at a $100 price.

```
fleet_target_usd 1000.0
opening_spendable_usd 1000.0
opening_locked_usd 1000.0
spendable_usd 1000.0
locked_usd 1000.0
realized_profit_usd 0.0
mature_profit_usd 0.0
bots_open 5 mature_positions 0 growth_pct 200.0
```

## Maturity fires at the live threshold and is silent under it

Two-sided. The same five balances, priced either side of 200 percent growth.

```
price x2.99  mature=0.00     positions=0  locked=2990.00
price x3.00  mature=2000.00  positions=5  locked=3000.00
price x3.01  mature=2010.00  positions=5  locked=3010.00
```

The rule is `src.trading.smart_wire.mature_profit_usd`, imported. Paper writes
no second definition.

## The fleet changing moves both opening figures

```
six bots  -> opening 1200.0 spendable, 1200.0 locked
four bots -> opening 800.0 spendable
```

`opening_ledger` runs on every press of Start, so the change lands on the next
press and never inside a run.

## A pretend trade closes and Realized moves

350 real 1h BTC/USD bars were read from the public market endpoint. A balance
was opened at the window's low bar, then `tick` walked the later bars.

```
bars 350  open at 204  76563.52  last 77781.04
bar 218 scrum usd=3.20 realized=0.0000 tranches 1
bar 228 scrum usd=2.14 realized=0.0000 tranches 2
bar 232 scrum usd=5.98 realized=0.0000 tranches 3
bar 252 fold  usd=3.77 realized=-0.5867 tranches 2
fills 4  units 0.002517114587378317  cash 207.49  basis 192.88
```

The fold closed the tranche the first scrum opened. Its proceeds were $3.18 net
and the buy-back spent $3.77, so the closed cycle realized -$0.5867 in cash
while the units rose. Nothing was placed at a venue.

## The log carries both halves and Validation reads it

53 rows were written by `record`, five of them carrying a fill. Every row was
read by the Simulator's own gate-log reader and every trade half constructed a
`YtdTrade`.

```
rows 53
validate_entry + row_from_entry read 53 of 53
GATE HALF  1788875706475 p0 BTC/USD coinbase scrum False fold True fixtures True True
TRADE HALF YtdTrade(id='paper-p0-1788875706475-BUY', ts_ms=1788875706475,
           side='BUY', amount=5.36233014755001e-05, price=77788.88,
           cost=4.196475416178572, fee=0.02517885249707143, fee_currency='USD')
LEDGER     {'fleet_target_usd': 1000.0, 'opening_spendable_usd': 1000.0,
            'opening_locked_usd': 1000.0, 'spendable_usd': 203.2901,
            'locked_usd': 199.9748, 'realized_profit_usd': -2.6576,
            'mature_profit_usd': 0.0, 'mature_growth_pct': 200.0}
CONTROL    gate.log data misses 'fold_blockers'
```

The control removed one required field from a parsed row; the reader refused it.

## Gate labels come from one place

The row records the blocker phrases the chain produced and the labels
`gate_for_blocker` maps them to.

```
scrum_blockers ['delta≤0', 'TA-not-bullish(dir=BEARISH)',
                'scrum_ok=False(bb_pos=0.00)',
                'BB-below-upper-detect(bb_pos=0.00<0.88)',
                'efficiency_ratio_regime(ER=0.854≥0.70; ...)',
                'zscore_extremity(z=-2.69<-2.0; ...)']
scrum_gates    ['TGT', 'TA', 'BB']
```

Two blocker phrases map to no label and are reported in `unmapped_blockers`
rather than dropped. `_BLOCKER_PREFIXES` in `src/trading/gate_vocabulary.py`
carries no entry for the efficiency-ratio and z-score gates, so the 19-light row
cannot represent them. That is a live file and adding a label would change what
the light row shows, so it is recorded here and named on the issue, not changed.

## Both hosts print the same line

One live run of five paper bots. The Qt widget was built offscreen and the
React panel was rendered in a Chromium view from `desktop/renderer/index.html`.

```
MODEL   Paper Spendable $1,007.49  |  Paper Locked $999.98  |
        Paper Realized Profits $-0.59  |  Paper Mature Profits $0.00
QT      Paper Spendable $1,007.49  |  Paper Locked $999.98  |
        Paper Realized Profits $-0.59  |  Paper Mature Profits $0.00
REACT   {"paper-ledger-title":"Paper Ledger",
         "paper-ledger-figures":"Paper Spendable $1,007.49  |  Paper Locked
          $999.98  |  Paper Realized Profits $-0.59  |
          Paper Mature Profits $0.00",
         "paper-ledger-opening":"5 paper bots, $1,000.00 fleet target.
          Opens $1,000.00 spendable and $1,000.00 locked."}
DATASET {"spendable":"1007.4865862934162","locked":"999.9773788214663",
         "realized":"-0.5866864687209303","mature":"0"}
```

The control is the run itself: the same reading taken before any fill printed
$1,000.00, $1,000.00, $0.00, $0.00 in both hosts, so the agreement above is on a
moved value and not on a default.

## The figures never reach the live ledger

`PaperRun` holds the four figures in memory. `PaperFleetSource` reads
`bot_state.json` and raises `SendRefused` for every name outside its read set,
so no paper figure has a path back into the stored record. The only file a run
writes is the paper log under its own root.

```python
PAPER_ROOT: Path = Path.home() / ".acervator_paper"
```

`tests/conftest.py` watches that root beside the other three and redirects the
writer at `ACERVATOR_PAPER_ROOT`, so no future test can write into it.
