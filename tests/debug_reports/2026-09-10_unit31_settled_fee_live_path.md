# The venue fee reaches a fill on the live path - what each run printed

Reference. Subjects: `src/trading/scrumming/execution.py`,
`src/trading/scrumming_bot.py`,
`docs/manual/08-tabs/proof-of-accumulation.md`.

Every run below used `python -X dev -X faulthandler` with `PYTHONWARNINGS=error`.
No test was written. `main.py` was never launched, because the instance guard it
builds writes into the runtime folder and the operator is trading on this machine.
The construction seams used instead were the program's own:
`BotManager.restore_bots_from_state` over a copy of `bot_state.json`,
`CapitalReservationRegistry` through `set_registry` pointed at a copy of
`reservation_state.json`, and `SharedTestnetBridge.install_on` with all seven of
its paths under a scratch folder. Every run restored 38 bots and drove bot
`650df31a`, whose market is `PUMP/USD` on coinbase. The first lines of every run
read the logging handlers the imports had attached; the root logger and
`acervator` both held none.

## The error

### Every live fill announced a refusal while the venue held the fee

The two paths a bot trades on read the fee off the body `create_order` returned,
never off a settled order. On Coinbase that body carries no fee, so
`_fill_fee_fields` answered `the venue reported no fee` and the award distilled
nothing.

```
src/trading/scrumming/execution.py:1551   _execute_sell  (SCRUM, DIST)
src/trading/scrumming/execution.py:1974   _execute_buy   (FOLD, ENTRY, HEDGE)
src/trading/scrumming_bot.py:2152         self_destruct  (SELF_DESTRUCT)
```

Driven on the commit this branch forked from, `1ac2de72`, with the venue's own
settled body holding the operator's real fee and the platform free to ask for it:

```
base sell_settled_fee    get_order per fill 0   fee_refusal 'the venue reported no fee'
base buy_settled_fee     get_order per fill 0   fee_refusal 'the venue reported no fee'
base destruct_settled_fee get_order per fill 0  fee_refusal 'the venue reported no fee'
quintessence minted      0 on all three
```

### The cause named by the previous unit does not hold on Coinbase

The previous unit's closing line reads that `_settled_fill` re-reads the order
only when the first read shows no fill. On Coinbase the placement body always
shows no fill, so that re-read always runs and is not where the live path loses
the fee. `_execute_sell` and `_execute_buy` never call `_settled_fill` at all.

## Reproduction

```
cd <worktree>
PYTHONPATH=<worktree> PYTHONWARNINGS=error QT_QPA_PLATFORM=offscreen \
  python -X dev -X faulthandler <scratch>/U31_drive_settled_fee.py \
  <scratch>/U31_branch_<arm> <arm>
```

Eight arms: `sell_settled_fee`, `sell_unsettled`, `buy_settled_fee`,
`buy_unsettled`, `destruct_settled_fee`, `destruct_unsettled`,
`sell_read_rate_limited`, `sell_read_never_answers`. Each one runs against this
branch and against `1ac2de72`, and `U31_compare_figures.py` reads the two result
files.

The venue is a stand-in that answers `place_order` with Coinbase's
`success_response` body and `get_order` with Coinbase's historical-order body,
both put through `CCXTConnector._parse_order`, which is the parser the live path
uses. Two inputs are named rather than hidden.

```
the fee on the settled body   the operator's own Coinbase statement row for
                              that exact trade
the emission on an activation  never set, so the award gate answers
                              no_activation_named and the mint is driven through
                              QuintessenceLedger.distil
```

No authenticated call was made to Coinbase. `~/.acervator/coinbase_credentials.json`
is closed by this repository's own rule, and the key behind it is held in an
encrypted vault.

## The cause

### What each Coinbase call returns, and when

Read from the replies recorded in `ccxt/coinbase.py`, version 4.5.77, which are
the venue's own published bodies.

```
create_order -> success_response
    order_id, product_id, side, client_order_id
    no total_fees, no filled_size, no average_filled_price, no status

fetch_order, order still open
    status OPEN    settled False  filled_size 0                total_fees "0"

fetch_order, market order settled
    status FILLED  settled True   filled_size 0.000297920684505
    average_filled_price 21220.6399999973697697
    total_fees 0.0379324055666004
```

`parse_order` maps `total_fees` to `fee.cost` and names the fee currency from the
market's quote. `CCXTConnector._parse_order` reads `fee.cost` into `Order.fee`.
`fetch_order` is therefore the one call that carries a fee, and it carries one
only once the venue marks the order settled.

### The platform already had the call

```
src/exchange/ccxt_connector.py:1171   get_order   -> fetch_order
src/exchange/ccxt_connector.py:1184   get_my_trades -> fetch_my_trades, fee.cost
src/exchange/position_health.py:90    sums t.fee from those Trade records
src/trading/scrumming/execution.py:177  _settled_fill already calls get_order
```

`get_order` takes the order id and the symbol, so a settled order is re-readable
by its own id.

### The operator's own placements agree

```
~/.acervator_logs/console/system.log
ORDER_PLACED | BUY order accepted by exchange | ID=d4100f08-... status=open filled=0.0/2672.0
9 of 9 ORDER_PLACED records read status=open filled=0.0
0 records read status=filled or status=closed
0 'booking the ESTIMATE' messages
```

His trade log holds 1,710 rows and none carries a fee field, because the running
instance predates the previous unit's merge.

## The correction

### One read, after the fill, for the fee alone

`_settle_venue_fee` re-reads the order by its id and writes only
`_last_fill_venue_fee`. The units and the price come from the fill rather than
from the second reply, and `_last_sell_venue_fee` is never touched, so a sale's
proceeds still book exactly as before.

```python
    _VENUE_FEE_REREADS = 1
    _VENUE_FEE_REREAD_DELAY_S = 0.2
```

Called at four points, all after the order is placed and the fill is known:

```
_settled_fill, placed body carried a fill        execution.py
_settled_fill, re-read body carried a fill       execution.py
_execute_sell, after _record_venue_fee           execution.py
_execute_buy, after the fill record is written   execution.py
self_destruct, after the fill record is written  scrumming_bot.py
```

### The call count, and what a failed call costs

Each row below was driven, and the count is the stand-in venue's own record of the
calls it was asked for.

```
sell_fee_at_placement    get_open_orders, get_markets, place_order
                         get_order 0, fee_usd 0.062153808
sell_settled_fee         get_open_orders, get_markets, place_order, get_order
                         get_order 1, fee_usd 0.062153808
sell_read_rate_limited   get_order 1, fee_refusal, sold 1409 @ $0.003676
sell_read_never_answers  get_order 1, fee_refusal, sold 1409 @ $0.003676
```

`get_order` carries `@_with_retry(max_retries=3, base_delay=1.0)` and the
connector's own 25-second ceiling, which are the same bounds every other venue
read in the platform already has.

### The await lands where no second tick of the same bot can reach

`BotContainer._run_with_guard` holds one task per bot and awaits `tick` to
completion in a `while` loop, so the 0.2-second yield cannot admit a second tick
of the same bot. The yield sits after holdings and the trade counters are written
and before the caller books the tranche, which moves the moment of that booking by
up to 0.2 seconds and changes none of its figures.

## The rerun

### Both sides earn, from the settled read

```
SELL  PUMP/USD 1409 @ $0.003676
      venue calls  get_open_orders, get_markets, place_order, get_order
      get_order per fill 1
      fee fields   {'fee_usd': 0.062153808}
      distilled    0.0621538080 Quintessence, conservation balanced, delta 0E-10

BUY   PUMP/USD 1325 @ $0.002286
      venue calls  get_open_orders, get_balance, get_markets, place_order, get_order
      get_order per fill 1
      fee fields   {'fee_usd': 0.0363474}
      distilled    0.03634740 Quintessence, conservation balanced, delta 0E-8
```

### The emitted fill event carries the figure

The self-destruct path emits `trade.filled` itself, so the payload was read off
the bus rather than off the helper.

```
{'type': 'SELF_DESTRUCT', 'side': 'SELL', 'amount': 13262.0, 'price': 0.003676,
 'usd': 48.751112, 'profit': 0.0, 'operator_initiated': True,
 'symbol': 'PUMP/USD', 'exchange': 'coinbase', 'fee_usd': 0.062153808}
```

Against `1ac2de72` the identical payload carries
`'fee_refusal': 'the venue reported no fee'` and every other value is the same.

### An unsettled order earns nothing and says why

The venue's own open-order body reports `total_fees "0"` and `settled false`.

```
sell_unsettled      fee_refusal 'the venue reported no fee'   0 Quintessence
buy_unsettled       fee_refusal 'the venue reported no fee'   0 Quintessence
destruct_unsettled  fee_refusal 'the venue reported no fee'   0 Quintessence
```

### No figure a bot trades on moved

Eight drives, 24 figures each, compared between `1ac2de72` and this branch.

```
order sent to the venue, the fill price, holdings, the target balance, the
anchor target, the fold queue, the standing surplus, the last trade price and
side, both hysteresis references, both armed flags, the quote conversion, the
distribution accumulator, the hedge balance, every main lot, every fold tranche,
and seven running totals

trading differences   0 of 24, on all eight drives
```

The control sits in the same comparison. The fee field rides in the same
dictionary as the 24 figures, and the comparison reports it on the three drives
where a fee arrived.

```
sell_settled_fee      1 difference  fill_event_fee_fields
buy_settled_fee       1 difference  fill_event_fee_fields
destruct_settled_fee  1 difference  fill_event_fee_fields
the five other drives 0 differences
```

### Demo mode reads the fee over a second chain

Two `SharedTestnetBridge.install_on` calls, each with its own seven paths, and no
flag selects between them.

```
the same class        : CertificationSocket and CertificationSocket
the same chain object : False
the same ledger       : False
DEMO fee_usd 0.062153808 -> 0.0621538080 Quintessence, balanced True
```

### Nothing was written under the runtime tree

```
~/.acervator/reservation_state.json  last written 04:00:30, before this work
~/.acervator/bot_state.json          saved_at_human 2026-09-10 05:16:55, the
                                     application's own save stamp at its own
                                     five-minute cadence
```

Every bridge path, every registry path and every identity file was given
explicitly under the scratch folder.

### The lanes and the archetypes

```
python -m tools.local_ci --lane black    VERDICT: PASSED, 413 files, 1 lane ran
python -m tools.local_ci --lane flake8   VERDICT: PASSED, 1 lane ran

execution.py      coding_archetype  passed=True  ta_archetype  passed=True
scrumming_bot.py  coding_archetype  passed=True  ta_archetype  passed=True
proof-of-accumulation.md  docs_archetype  passed=True
```

Every tool reported `ok` in `tool_availability` and every `errors` list was empty.
The fixture pairs were driven first: coding `known_good` exit 0 `passed=True` and
`known_bad` exit 1 `passed=False`; TA `known_good_ta004` `passed=True` and
`known_bad_ta004` `passed=False`; docs `known_good` `passed=True` and `known_bad`
`passed=False`.

## What is not proved here

No call reached the live Coinbase endpoint. The fee figures are the operator's own
statement rows placed in the venue's own recorded reply body and read through
`CCXTConnector._parse_order`.

A partly filled order reports `total_fees` for the part filled at the moment of
the read. The fill's own units and price are booked from the placed reply, so the
fee can be smaller than the fee for the whole order.

The award gate answered `no_activation_named` on every drive, because no
activation sets an emission. The Quintessence figures come from
`QuintessenceLedger.distil`, the call `certify` makes when an award is granted.

Nothing subscribes certification to the live fill event.
