# The ATA-SMP Chart List, And The Two Errors Found Running It

**Mode: Reference.**

The Charts tab drew one list of markets: the assets the bots trade. It now draws
two, chosen by a Live / ATA-SMP toggle above the blue arrows and the ticker
menu. ATA-SMP is the markets that reached the Ready to Send bucket.

Nothing here was measured against a running Acervator. No process was started,
attached to or queried, no order was touched, and no exchange call was made.
`~/.acervator/settings.json` hashed `18d380c7134dadbb2acbf5cbe5527ea177fe8b23cc77eb3fff6334fb03feeac8`
before the work and the same after it.

## What puts a market on the list

`PushBoard.watched_markets` in `src/trading/ata_spm_push.py` answers one row per
market. It reads three holders of a called market, oldest first: the calls
phase seven settled, the calls it still watches, and the posts in the bucket.
The bucket is the trigger the directive names, and phase seven's memory is what
keeps a market listed after a later scan replaces the bucket's posts.

Phase seven kept only the key of a settled call, which cannot name the market
later. It now keeps the call, so a settled market is still listed with its
ticker, its timeframe and its vote. The settled calls are read in key order, so
the answer does not follow the dictionary.

The Charts tab stores no markets of its own. `TradeChartsTabModel.ata_source`
and `TradeChartsTab.set_ata_source` take that reader, and
`MarketInspectorTabMixin._wire_ata_chart_list` binds it. One set, two readers.

## The errors the runs reported, and the corrections

### The renderer's arrows called the bridge and nothing moved

`trade_charts_tab.js` sends `step_by` and `pick_at` to `trade_charts_tab.state`.
`view_model` read every other request field and passed neither on.

```
after open      shown: 0 BTC/USD
after step_by 1 shown: 0 BTC/USD
after pick_at 2 shown: 0 BTC/USD
```

Reproduced by calling the bridge handler directly under
`PYTHONWARNINGS=error python -X dev -X faulthandler`. The handler now forwards
`step_by`, `pick_at` and `toggle_list` to `build_view_model`, which already took
the first two.

```
after open      shown: 0 BTC/USD
after step_by 1 shown: 1 ETH/USD
after pick_at 2 shown: 2 SOL/USD
after toggle    mode: ata_smp  ATA-SMP  ['No called market']  0 of 0
after toggle back     mode: live  SOL/USD
```

### The renderer refused every real payload

Handing the surface's own view model to `trade_charts_tab.js` inside
`QJSEngine` threw before a row was placed.

```
ReferenceError: STRETCH_SLOTS is not defined
```

`checkSlots` read that name and the file declares it nowhere. The line is
`!owns(content, LAYOUT_SLOTS) || !owns(content, STRETCH_SLOTS)`, so it threw
only once `layout_slots` was present — that is, on every payload the surface
publishes and on none of the short ones a reader would try first.

The arithmetic beside it, `layout_slots == mounted + stretch_slots`, described
the old tab that mounted one panel per bot. The check now compares the row count
the surface declares against the row count this module draws, which is the
disagreement it exists to catch. Driven with `layout_slots` set to 3 it reports:

```
[{"where": "content", "field": "layout_slots", "fault": "disagrees", "detail": 4}]
```

and with the published value it reports `[]`.

## Both hosts, driven and compared

The Qt widget and the Qt-free surface were built over one set of bot statuses
and one `PushBoard` holding three called markets, then read against each other
on the toggle and both its states, the arrows, the ticker menu, the readout, the
position text and the plotted symbol.

```
Live list   matched 19 of 19
ATA-SMP     matched 19 of 19
```

The same reads over the two real lists differ on 5 of 19, so the comparison was
watched reporting a difference before its agreement was read as one.

The renderer module was then handed the surface's ATA-SMP view model.

```
renderer faults : []
renderer mode   : ata_smp
renderer order  : ["DOT/USD", "LINK/USD", "AVAX/USD"]
renderer    matched 4 of 4
```

Every measurement above was taken twice, once under `ACERVATOR_VARIANT=qt` and
once under `ACERVATOR_VARIANT=react`. The two runs agree on every printed value.

## The arrows walking the ATA-SMP list

Three markets reached Ready to Send. `LINK/USD` was called on two timeframes and
appears once.

```
watched markets: [['DOT/USD', 'bull', ['1w']],
                  ['LINK/USD', 'bull', ['1h', '1d']],
                  ['AVAX/USD', 'bear', ['1d']]]

surface walk: ['DOT/USD', 'LINK/USD', 'AVAX/USD', 'DOT/USD']
qt walk     : ['DOT/USD', 'LINK/USD', 'AVAX/USD', 'DOT/USD']
```

The list wraps, as the Live list does.

## The empty state

With no reader bound, and with a bucket holding nothing, the list draws its own
absence rather than nothing.

```
items          : ["No called market"]
position_text  : "0 of 0"
stepping_enabled: false
hint           : "A market joins this list when it reaches Ready to Send."
source_bound   : false
order          : []
```

No entry is written that the reader did not answer. A reader that raises leaves
the list as it was and records the refusal.

## What the operator sees differently

A button above the blue arrows reading Live or ATA-SMP. Pressing it moves the
arrows and the ticker menu to the markets the TA engine has called and queued,
so a called market can be watched long after its post has gone. Pressing it
again returns to the traded assets, at the asset that was on screen. The React
half of this tab draws its arrows and its ticker for the first time.

## What is not done

An ATA-SMP market carries no exchange id, so its candles come from the fetcher's
default source rather than the venue the call was read on.
