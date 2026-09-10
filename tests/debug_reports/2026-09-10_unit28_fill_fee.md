# A fill event carries its venue fee - what each run printed

Reference. Subjects: `src/trading/scrumming/execution.py`,
`src/trading/scrumming/tick_phases.py`, `src/trading/scrumming_bot.py`,
`src/core/emit_contracts.py`, `src/core/logging_engine.py`,
`src/competition/certification_socket.py`,
`docs/manual/08-tabs/proof-of-accumulation.md`.

Every run below used `python -X dev -X faulthandler` with `PYTHONWARNINGS=error`.
No test was written. `main.py` was never launched, because the instance guard it
builds writes into the runtime folder and the operator is trading on this machine.
The paths used instead were the program's own construction seams:
`BotManager.restore_bots_from_state` over a copy of `bot_state.json`,
`CapitalReservationRegistry` through `set_registry` pointed at a copy of
`reservation_state.json`, and `SharedTestnetBridge.install_on` with all six of its
paths under a scratch folder. The first lines of every run read the logging
handlers the imports had attached; the root logger and `acervator` both held none.

## The error

### No fill carried the fee the venue charged

`CertifiedFill.fee_usd` reached `QuintessenceLedger.distil` as the amount a fill
earns. The ten `trade.filled` emit sites carried no fee field, so every fill built
from that payload read `0.0`, and the award path refused `nothing_to_award` on
every real trade. All 1,709 entries in the operator's trade log carry no fee.

```
before this unit
  src/core/emit_contracts.py  trade.filled optional fields
    type, usd, profit, operator_initiated
  no fee on any of the ten emit sites
  no fee in the log row LogManager._on_trade_filled_bus writes
```

### The buy side held no fee record at all

`_record_venue_fee` stored the fee for a settled sell and set the record to None on
a buy. `_execute_buy` never called it. A Fold is a buy and the venue charges for
it, so the buy side had nothing to carry even if an emit site had asked.

```
before this unit
  _record_venue_fee      sell -> store, buy -> clear
  _execute_sell          calls it
  _execute_buy           does not call it
```

## Reproduction

```
cd <worktree>
PYTHONPATH=<worktree> PYTHONWARNINGS=error QT_QPA_PLATFORM=offscreen \
  python -X dev -X faulthandler <scratch>/U28_drive_fill_fee.py <scratch>/U28_run \
  "<his Coinbase transaction exports>"
```

The run reads his fills through `src/trading/live_log_reader.py` `live_trades`,
matches each to its row in his own Coinbase transaction export by asset, size and
second, restores his real 38-bot fleet from a copy of `bot_state.json`, drives the
real `_execute_manual_rebalance` with a stand-in venue that returns one prepared
order body through `CCXTConnector._parse_order`, and puts the emitted payload
through `CertificationSocket.certify`.

Two inputs are supplied rather than measured, and both are named rather than
hidden.

```
the activation's Quintessence figure   an argument; the design fixes the split
                                       and the share, never the total
the six-month project age answer       a stand-in through MarketRotation's own
                                       constructor seam, as the previous unit did
```

The fee itself is not supplied. It is the figure in his Coinbase transaction
export for that exact trade, placed in the order body's `fee.cost` field, which is
where `ccxt_connector.py` reads a fee from for every real order.

## The cause

### Every consumer of the fill event, read before the payload changed

```
src/competition/certification_socket.py:485   _on_trade_filled builds a
                                              CertifiedFill and reads fee_usd
src/core/logging_engine.py:540                _on_trade_filled_bus writes the
                                              trade.log row
src/gui/live_bot_window.py:283                _on_trade_filled appends one
                                              activity line from side, symbol,
                                              amount and price
src/gui/main_window.py:220                    _on_trade_filled_sfx plays a sound
                                              from type and profit
src/gui/main_tabs/live_bot_window_surface.py:551  on_trade_filled appends one
                                              activity line
```

Each reads named keys. An added key is inert for the three screen consumers.
`src/core/emit_contracts.py` declares required and optional fields and reports a
missing required field only, so an added optional field breaks no observer.

Records already written carry no fee field. `live_log_reader.py`
`TRADE_LOG_REQUIRED_DATA_FIELDS` does not name one, so every existing row stays
valid and readable. The history screen and the grading path read action, symbol,
side, amount, price and usd, and none of them reads a fee, so no existing consumer
changes behaviour on an old row. Rows written from here on carry either `fee_usd`
or `fee_refusal`.

### Why the buy side was discarded

`git log -S_record_venue_fee` reaches `f907cc79`, which introduced the record. Its
message states the purpose: a venue credits the NET on a sale, so a sale's
proceeds had to have the venue's fee taken out of them. A purchase has no
proceeds, so the record was scoped to sales and cleared on a purchase to stop a
stale sale fee reaching a later sale. The scope was correct for that job. It was
never a decision that a purchase has no fee.

The same message records the measurement that still governs what a live Coinbase
fill can carry: `create_order` returns a four-key body with no `total_fees`, so
`Order.fee` is `0.0` on every just-placed Coinbase order, and `fetch_order` is the
endpoint whose body carries one.

## The correction

### One fee record for either side, read only by the fill event

`SettledSellFee` is now `SettledFillFee`, because it holds the fee for a fill on
either side. `_record_venue_fee` writes `_last_fill_venue_fee` on both sides and
keeps `_last_sell_venue_fee` exactly as it was, sell-only and cleared on a buy.
`_execute_buy` writes the fill record directly and never touches the sale record.

`_fill_fee_fields` consumes the fill record and returns the event's fee fields.

```python
        return {"fee_usd": _fee_usd}
```

```
no settled order was held for this fill
the venue reported no fee
the reported fee belongs to a different fill
the venue named no fee currency
the venue charged the fee in <currency>, not the <quote> this fill is priced in
no <quote>-to-USD rate is cached
the reported fee converts to nothing in USD
```

Ten emit sites spread the fields in: three in `execution.py`, four in
`tick_phases.py`, three in `scrumming_bot.py`.

### The order paths, driven

```
_execute_sell then _settled_sale_proceeds
   fill=0.003676
   proceeds booked=5.117330192000001
   _fill_fee_fields(0.003676) -> {'fee_usd': 0.062153808}
   read a second time      -> {'fee_refusal': 'no settled order was held for this fill'}

_execute_buy
   fill=0.002596
   _fill_fee_fields(0.002596) -> {'fee_usd': 0.078939168}
   read a second time      -> {'fee_refusal': 'no settled order was held for this fill'}
```

The sale record is spent by `_settled_sale_proceeds` and the fill record survives
it, which is what the SCRUM and DIST sites need. The second read shows the record
is spent once, so a stale fee cannot attach to a later fill.

## The rerun

### Both sides earn, on his own trades and the venue's own fees

```
SELL  PUMP/USD 1409 @ $0.003676        2026-08-20 15:02, bot 650df31a
      venue row 6a8716ec03b6f3f5c260f0f6  fee $0.062153808
      emitted   fee_usd 0.062153808
      awarded   0.0310769040 Quintessence, pool coinbase:1|PUMP/USD

BUY   PUMP/USD 1325 @ $0.002286         2026-08-07 20:35, bot 650df31a
      venue row 6a7641a1facc93c97c34e93b  fee $0.0363474
      emitted   fee_usd 0.0363474
      awarded   0.03634740 Quintessence
```

### A fill with no venue fee earns nothing and says why

A separate participant per case, so the refusal is the absent fee rather than the
cooldown the previous award opened.

```
emitted   fee_refusal 'the venue reported no fee'
refused   nothing_to_award
distilled 0 Quintessence
```

### No figure a bot trades on moved

The same four drives were run on `bfed8e77`, the commit this branch forked from,
and on the branch. Twenty-four figures per drive, including the order sent to the
venue, every lot, every tranche, the hysteresis references, the quote rate and
seven running totals.

```
sell with a fee      24 figures identical
sell with none       24 figures identical
buy with a fee       24 figures identical
buy with none        24 figures identical
```

The same comparison applied to the payload reports one difference, which is the
control proving the comparison can report at all.

```
+ "fee_usd": 0.062153808
```

Varying the fee on one tree moves `_fold_queue_usd`, the new tranche's dollars and
`stats.total_scrummed_usd`, because `_settled_sale_proceeds` already booked a sale
net of a reported fee and gross without one. That behaviour is unchanged by this
unit, and the cross-tree comparison above is what isolates it.

### His records carry the fee

```
with a fee  {'action': 'CARTRIDGE_SCRUM', ..., 'usd': 5.117330192000001,
             'fee_usd': 0.062153808}
with none   {'action': 'CARTRIDGE_SCRUM', ..., 'usd': 5.179484,
             'fee_refusal': 'the venue reported no fee'}
```

### Demo mode reads the same fee over a second chain

```
the same class        : CertificationSocket and CertificationSocket
the same chain object : False

BTC/USD, venue fee $0.1369262274012 -> awarded 0.1369262274012 Quintessence

live ledger   total ever minted 0.067424304     balanced
demo ledger   total ever minted 0.1369262274012  balanced
```

### Nothing was written under the runtime tree

Both registries logged the scratch paths they were given, and
`CapitalReservationRegistry._save` writes only to the path it holds. The live
`reservation_state.json` and `bot_state.json` both changed during the session at
times when no process of this unit was running, which is the live application
writing them.

```
CapitalReservationRegistry loaded 38 reservations from <scratch>/U28_run/reservation_state.json
```

### What is not proved here

Six of the ten emit sites were not driven end to end. The four in `tick_phases.py`
and two of the three in `scrumming_bot.py` sit behind the tick gates, and the
mechanism they read is the `_execute_sell` and `_execute_buy` result shown above.
`self_destruct` places its own order and writes the fill record from the same
helper.

A live Coinbase fill will usually carry the refusal rather than a figure, because
`create_order` returns no fee and `_settled_fill` re-reads the order only when the
first read shows no fill.
