# The capture bounds and the grade curve — what each run printed

Reference. Subjects: `src/competition/capture_bounds.py`,
`src/trading/trade_grader.py`, `src/competition/__init__.py`,
`src/exchange/history_read_contract.py`, `src/gui/shared_testnet.py`,
`docs/manual/08-tabs/proof-of-accumulation.md`.

Every run below used `python -X dev -X faulthandler` with `PYTHONWARNINGS=error`.
No test was written. `main.py` was never launched: `main.py:812` builds an
instance guard whose `take_ownership` writes into the runtime folder, and the
operator is trading on this machine, so `SharedTestnetBridge.install_on` was
called directly with every runtime path redirected into a scratch folder. The
first lines of the run read the logging handlers the imports had attached, and
both the root logger and `acervator` held none, so nothing reached the live log
tree.

## The error

Two faults in the award path, both found by grading real Coinbase fills.

### A trade nothing could grade paid half rate

`src/trading/trade_grader.py` averages four sub-scores and answers `0.5` when no
axis had inputs. The award is linear in the grade, so a trade carrying no
reference price and no later prices collected half the full rate.

```
no reference price, no future prices
  scored_axes 0   overall_numeric 0.5   overall D   rationale 'no context available'
```

A grade of `0.5` and a grade the code defaulted to `0.5` were the same number to
every reader, so no caller could tell a measurement from a default.

### The execution axis states nothing past one per cent

`src/trading/trade_grader.py` scored execution as `1.0 - bps / 100.0`, clamped to
`[0.0, 1.0]`. A fill a hundred basis points worse than its reference scores zero
and so does one fifty per cent worse; a fill a hundred points better scores one
and so does one twelve per cent better.

One real Coinbase market, down twelve per cent on the day, graded top marks:

```
VVV/USD fill 24.3633 against its 24h open 27.6914
  execution_score 1.0   execution_bps -1201.85   scored_axes 1   overall A+
```

The code matches its own docstring, so nothing lies. The consequence is that past
a hundred basis points the number multiplying the award is a clamp and not a
reading of the fill.

### A bound on the distance alone would have refused seven awards in eight

The first repair refused any award whose `execution_bps` lay past the span, in
either direction. That bound was never measured against the operator's own trading
before it was written, and the measurement refutes it.

`src/trading/live_log_reader.py` `live_trades` reads his `trade.log`, and
`src/exchange/history_read_contract.py` `graded_row` grades each row the way the
History screen does. 1,709 entries, 1,668 gradeable, 1,560 carrying a reference
price:

```
past a hundred basis points       1368   87.69%
  favourable                      1154   73.97%
  adverse                          214   13.72%

inside the span                    192   12.31%
the signed spread, basis points
  p0   -5030.57   p5  -1915.52   p25 -1064.05   p50  -552.35
  p75    -78.69   p95   556.75   p100 3253.80
```

The reference `graded_row` builds is the median of up to five prior same-asset
trade prices, not a decision-time quote. A Scrum sells above its earlier fills and
a Fold buys below them, so a wide favourable gap is the strategy rather than
slippage, and the median fill sits 552 basis points away on that side.

## Reproduction

```
cd <worktree>
PYTHONPATH=<worktree> PYTHONWARNINGS=error python -X dev -X faulthandler \
  <scratch>/U10_drive_bounds.py <scratch>/U10_run
```

The run connects the platform's own `CCXTConnector` to Coinbase with no
credentials, fills a real `MarketPairsScout` from `get_all_tickers`, installs the
bridge, and then calls `CaptureBounds` methods. Every volume, price and 24-hour
move below is the venue's.

Two inputs are supplied rather than measured, and both are named rather than
hidden. The activation's Quintessence figure is an argument, because the design
fixes the split and the share and not the total. The six-month project age rule is
answered by a stand-in lookup passed in through the rotation's own constructor
seam: live CoinGecko coverage leaves the real Coinbase pool at 5 eligible
markets, under the floor of 12, which unit 9 already drove and recorded.

## The cause

### Every consumer of `grade_trade`, read before anything changed

```
src/exchange/history_read_contract.py:483   grade_trade(record, context).overall
src/competition/rpg_metrics.py:151          reads overall_numeric off a grade
src/competition/rpg_metrics.py:144          reads the four sub-scores and the letter
src/competition/quintessence_ledger.py:171  amount = fee * rate * grade
docs/manual/08-tabs/history.md:170          quotes grade_trade
docs/manual/10-live-trade-history.md:789    quotes grade_trade
docs/manual/12-adr-index-and-glossary.md    quotes grade_trade
```

`TradeGrade(` is constructed in exactly one place, `trade_grader.py` itself, so no
caller builds one positionally.

### What the distance bound should have been, sized on the same records

The grade that cannot be trusted is the one with nothing in it but a clamp. When
accuracy is the only axis that scored and it has clamped, `overall_numeric` is
exactly 1.0 or exactly 0.0 and no reading of the fill survives in it.

```
rows carrying an execution_bps           1560
  clamped past the span                  1368   87.69%
  clamped AND accuracy the only axis        35    2.24%
    clamped at 1.0                          28
    clamped at 0.0                           7

two-axis rows past the span, which keep earning   1333   85.45%
  their letters   D 449   A+ 428   C 219   F 131   B 81   A 25

one-axis rows inside the span, which keep earning    3
```

Twenty-eight of his own fills carry a grade of exactly 1.0 derived from a single
clamp, which is the farming route. Refusing those costs 2.24% of graded fills
instead of 87.69%, and the 1,333 rows past the span with a second axis keep
earning, their letters spread across all six bands.

### Why the curve was not the thing to change

The operator closed the curve: the award is the fee times the grade, linear, no
exponent. Changing what the grade MEANS would move the letter the History tab
prints and the figures `rpg_metrics` reports to the PoA tab. The grade is
therefore untouched, and the award path carries both bounds instead.

### The share ceiling's last digit

`max_participant_share` is `pool * 5 / 100` at twenty-eight significant digits, so
twenty of them need not add up to the pool exactly. Measured across two runs of
the same code on two draws: in one, twenty awards at the ceiling left `5E-25`
unspent; in the other, the twentieth request for the full ceiling asked for `4E-25`
more than remained and was refused. Either way twenty distinct participants empty
the pool, which is the property the 5% figure was chosen for. A partial award is
not offered, because `poa_modes.PartialActionError` already sets that precedent in
this package.

### What the venue does and does not serve

Coinbase's plural ticker call carries no `bid`, `ask`, `low` or `high`. It carries
`last`, `open`, `percentage`, `vwap` and both volumes, so the reference price in
every grade below is the venue's own 24-hour opening price.

```
BTC/USD: last 78140.63  open 79572.14  percentage -1.79900905015248
         quoteVolume 404975607.15  baseVolume 5182.6509096
```

## The correction

One count on the grade, one named distance, and a refusal for each.

`src/trading/trade_grader.py` gains a field and a constant. The field says how
many axes scored, so a default `0.5` is distinguishable from a computed one. The
constant names the distance the axis states, which was a bare `100.0` inside the
expression and is now read by the award path as well.

```python
#: Slippage at which ``_score_execution`` reaches 0.0; past it the score clamps.
EXECUTION_SCORE_SPAN_BPS = 100.0

    scored_axes: int = 0

        scored_axes=len(sub_scores),
```

`src/competition/capture_bounds.py` holds the bounds. `activate` calls
`MarketRotation.eligible_pool` and `open_window`, which unit 9 left without a
caller, and sizes one pool a drawn market from the volume it carried at that
moment. `award` then refuses in this order: no allotment, no scored axis, a grade
resting on one clamped axis, a running cooldown, an allotment already taken, an
amount above the share ceiling, an amount the pool cannot pay. The grade bounds are
read first, so an ungraded trade never takes an allotment or opens a cooldown.

```python
        clamped = bps is not None and abs(float(bps)) > EXECUTION_READABLE_BPS
        if clamped and axes == 1:
```

`src/exchange/history_read_contract.py` gained the seam the measurement read
through. `graded_row` returns the whole `TradeGrade` and `grade_row` returns its
letter, so the History screen and any measurement of it share one grading path.

The cooldown is three candles of the awarding bot's own `ta_timeframe`, floored at
nine hundred seconds, and a timeframe the platform does not measure is refused
rather than given the shortest wait.

`src/gui/shared_testnet.py` builds it beside the rotation it reads, so every
launch has one and a TestNet run has its own over its own chain.

```python
        main_win._capture_bounds = bridge.install_capture_bounds(
            main_win._market_rotation, bounds_path
        )
```

## The rerun

Exit code 0, no warning raised as an error, every phase reached.

### Constructed by the running program

```
CaptureBounds installed (path=<scratch>/U10_bounds.json, activations=0,
cooldown 3 candles floored at 900s, 1 scored axis minimum)

bridge.capture_bounds         CaptureBounds
window._capture_bounds is it  True
holds the bridge's rotation   True
```

### The allotment, on real Coinbase volumes

```
coinbase season 1: 403 ranked, 20 eligible, draw 5
coinbase season 1: committed 5 of 20 markets as 6c0efc70b1d6d35a
coinbase:1 activated: 10000 Quintessence across 5 drawn markets

  BTC/USD    $404,975,607.15   pool 8849.253945898679744630403205   5% 442.4626972949339872315201602
  UNI/USD    $ 16,254,055.62   pool 355.1726654461578759652708877   5%  17.75863327230789379826354438
  PUMP/USD   $ 16,048,824.74   pool 350.6880986164634311579457240   5%  17.5344049308231715578972862
  SUI/USD    $ 12,378,533.61   pool 270.4873712360626776914103408   5%  13.52436856180313388457051704
  LTC/USD    $  7,981,113.83   pool 174.3979188026362705549698421   5%   8.719895940131813527748492105

  allotments sum 10000.00000000000000000000000   emission 10000   equal True
```

### The cooldown clock

```
    1m  3 candles     180s   cooldown     900s   floor binds
    3m  3 candles     540s   cooldown     900s   floor binds
    5m  3 candles     900s   cooldown     900s   three candles
   15m  3 candles    2700s   cooldown    2700s   three candles
    1h  3 candles   10800s   cooldown   10800s   three candles
    1d  3 candles  259200s   cooldown  259200s   three candles
    1w  3 candles 1814400s   cooldown 1814400s   three candles

     Elite turn candle 1m: 3 candles 180s, cooldown 900s
  Standard turn candle 5m: 3 candles 900s, cooldown 900s

the live fleet: 38 bots, ta_timeframe values ['5m']
  every bot on 5m waits 900s after an award
```

### Each bound, refused and paid

```
a grade no axis could score
  REFUSED  the grade on this trade scored 0 of four axes, so its 0.5 is the
           default and not a measurement; an award needs at least 1 scored axis
  PAID     FLOCK/USD against its 24h open: scored_axes 1, overall A+,
           LTC/USD awarded 1.0 Quintessence

a grade resting on one clamped axis
  REFUSED  this grade scored execution and nothing else, and its reference price
           sits -967.9 basis points from the fill, past the 100 the axis reads;
           a reference that far out is stale, so the one axis reports a clamp
           and the grade of 1.0 rests on nothing
  PAID     the same VVV/USD fill once a second axis scores: scored_axes 2,
           numeric 0.8333, overall B, 0.8333 Quintessence awarded

three candles, floored at fifteen minutes
  REFUSED  participant-scored has 1s left of a 900s cooldown of 3 5m candles;
           the gate pays nothing until it clears
  PAID     the same participant on UNI/USD the second the cooldown clears

one allotment a participant a market an activation period
  REFUSED  participant-scored already took an allotment of LTC/USD in
           coinbase:1; one allotment a participant a market an activation period
  PAID     participant-second on that same market, 1.0 Quintessence

at most 5% of a market's pool
  REFUSED  9.719895940131813527748492105 Quintessence is above the
           8.719895940131813527748492105 ceiling on LTC/USD, which holds a pool
           of 174.3979188026362705549698421; one participant takes at most 5%
           of a market's pool
  PAID     8.719895940131813527748492105, exactly the ceiling

the pool runs out
  REFUSED  allotment_exhausted, on a request for the full 13.52436856180313388
           ceiling against 5E-25 left of SUI/USD's pool
  PAID     twenty earners in turn, each taking the full ceiling

an unmeasured candle
  REFUSED  '7m' is not a candle the platform measures; the cooldown counts 3
           candles of the awarding bot's own timeframe, one of 1m, 3m, 5m, 15m,
           30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 1w

a window that cannot open
  REFUSED  pool_below_floor: kraken holds 0 eligible markets, under the floor
           of 12, so it draws nothing

a second activation of one exchange and season
  REFUSED  coinbase:1 is already activated and holds 5 market allotments

an award after the activation closed
  REFUSED  LTC/USD holds no Quintessence allotment in coinbase:1, so there is
           no pool for an award to come out of
```

### The narrower bound, driven on the operator's own fills

His graded fills, put through `CaptureBounds.award`. The pool in this run is
scaffolding so the bound is reachable; every grade, price and basis-point figure is
his. A favourable fill earns and an adverse one is refused, and the split is the
axis count rather than the direction.

```
one clamped axis, favourable fill
  2026-09-10 05:23  KAT/USD buy at 0.0052147215059309
  bps -1439.06   accuracy 1.0   axes 1   numeric 1.0   A+
  REFUSED  sole_axis_clamped

one clamped axis, adverse fill
  2026-09-10 07:21  RE/USD sell at 0.459
  bps +1085.65   accuracy 0.0   axes 1   numeric 0.0   F
  REFUSED  sole_axis_clamped

two axes, favourable fill past the span
  2026-09-10 03:22  KAT/USD buy at 0.005468
  bps -1023.25   accuracy 1.0   axes 2   numeric 0.5   D
  PAID     0.5 Quintessence

two axes, adverse fill past the span
  2026-09-10 00:10  SPK/USD sell at 0.01987
  bps +605.20   accuracy 0.0   axes 2   numeric 0.5   D
  PAID     0.5 Quintessence

inside the span
  2026-09-10 00:11  BILL/USD sell at 0.01338
  bps +0.86   accuracy 0.991411133119661   axes 1   numeric 0.9914   A+
  PAID     0.9914 Quintessence
```

### Demo mode

One class, two chains, the same `activate` and `award` path, no flag.

```
the bridge chain is the demo chain: False
one class, two chains: CaptureBounds CaptureBounds

  bridge chain: 25 CaptureBounds events, last QuintessenceAwarded
  demo chain:    1 CaptureBounds event,  last QuintessenceAwarded
    {"amount": "1.0", "cooldownUntil": 1000900.0, "exchange": "coinbase",
     "participant": "participant-scored", "season": 1, ...}

the demo participant a second time on the demo chain
  participant-scored already took an allotment of LIGHTER/USD in coinbase:1
```

### Three faults in the calling code, and what each one taught

None was a product defect, and each changed how the program was reached.

```
TypeError: object of type 'coroutine' has no len()
    CCXTConnector.get_all_tickers is a coroutine; the call needs asyncio.run
    and a connect("", "") before it

AttributeError: 'list' object has no attribute 'items'
    MarketPairsScout.ingest_tickers takes the venue's symbol-keyed dict

AttributeError: 'ChainEvent' object has no attribute 'name'
    the field is event_name
```

### What is not reached

Nothing in the live award path consults these bounds. `CertifiedFill` carries a
venue symbol, a fee and a grade, and no exchange, season or market pool, so
`CertificationSocket.certify` cannot name the activation an award would be drawn
from. Threading an activation through the socket is the award-path unit, and until
it lands the bounds are built and loaded on every launch and called by nothing.

One decision is recorded here rather than taken. The execution axis itself could
be widened so that a fill twelve per cent from its reference scores differently
from a perfect one. That would move `overall_numeric` and the letter on every
graded trade the History tab shows, which is a number the operator reads, so the
axis is unchanged and the measurement sits above.

The reference `graded_row` derives is not a decision-time quote, and the figures
above are a measurement of that derivation as much as of the fills. 87.69% of live
fills sitting past the span says the median of five earlier trade prices is a weak
stand-in for the price a decision was taken at. Whichever unit supplies a real
decision price will change every number in this section, and the narrow bound will
then refuse far fewer than 2.24% rather than more.
