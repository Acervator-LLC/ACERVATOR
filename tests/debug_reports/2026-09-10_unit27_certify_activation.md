# A certified fill names its activation - what each run printed

Reference. Subjects: `src/competition/certification_socket.py`,
`src/competition/capture_bounds.py`, `src/competition/__init__.py`,
`src/gui/shared_testnet.py`, `docs/manual/08-tabs/proof-of-accumulation.md`.

Every run below used `python -X dev -X faulthandler` with `PYTHONWARNINGS=error`.
No test was written. `main.py` was never launched: `main.py:812` builds an
instance guard whose `take_ownership` writes into the runtime folder, and the
operator is trading on this machine, so `SharedTestnetBridge.install_on` was
called directly with all six of its paths pointed at a scratch folder. The first
lines of the run read the logging handlers the imports had attached, and both the
root logger and `acervator` held none, so nothing reached the live log tree.

## The error

Two faults in the award path, both found by certifying real Coinbase fills.

### Nothing in the live award path consulted the bounds

`CertifiedFill` carried a venue symbol, a fee and a grade. It carried no
exchange, no season and no market pool, so `CertificationSocket.certify` could not
name the `Activation` an award would be drawn from and called
`QuintessenceLedger.distil` directly. Four bounds, a rotation, an eligibility rule
and a grade curve were built, loaded on every launch, and reached by nothing.

```
before this unit
  CertificationSocket.__init__ takes testnet, quint_ledger, competition_id,
  socket_path, mutation_lock
  CaptureBounds is named nowhere in certification_socket.py
```

### A fill with no fee would have passed every bound and spent the allotment

The venue's fee is absent from every `trade.filled` emit site, so a fill built
from that payload carries `fee_usd=0.0`. The award amount is the fee times the
grade, so the amount is zero, and zero is below the share ceiling and inside the
remaining pool. Every bound admitted it.

`CaptureBounds.award` would then have recorded the participant as having taken
their one allotment of that market for the whole activation period and opened a
900 second cooldown, for nothing.

```
SUI/USD sell at 0.8223, two scored axes, grade 1.0, fee 0.0
  amount 0 Quintessence
  0 > ceiling 40.8577          False
  0 + drawn > pool 817.1556    False
  -> granted, pays nothing, allotment spent, cooldown opened
```

## Reproduction

```
cd <worktree>
PYTHONPATH=<worktree> PYTHONWARNINGS=error QT_QPA_PLATFORM=offscreen \
  python -X dev -X faulthandler <scratch>/U27_drive_award_path.py <scratch>/U27_run
```

The run installs the bridge, connects the platform's own `CCXTConnector` to
Coinbase with no credentials, fills a real `MarketPairsScout` from
`get_all_tickers`, reads the operator's fills through
`src/trading/live_log_reader.py` `live_trades`, grades each one through
`src/exchange/history_read_contract.py` `graded_row`, and drives them into
`CertificationSocket.certify`.

Two inputs are supplied rather than measured, and both are named rather than
hidden.

```
the activation's Quintessence figure   an argument; the design fixes the split
                                       and the share, never the total
the six-month project age answer       a stand-in passed through MarketRotation's
                                       own constructor seam, because live
                                       CoinGecko coverage leaves Coinbase at 6
                                       eligible markets against a floor of 12
the per-fill venue fee                 1.0 where an award is driven, because no
                                       emit site and no log field carries one
```

## The cause

### Every consumer of `CertifiedFill`, read before the record changed

```
src/competition/certification_socket.py:171   certify takes one and signs it
src/competition/certification_socket.py:402   _on_trade_filled builds one
src/competition/__init__.py:44                re-exports the name
docs/manual/08-tabs/proof-of-accumulation.md:1072   names it in a table row
```

`certify` and `_on_trade_filled` are the only code that touches the record.
Nothing stores a `CertifiedFill`. The socket's own file holds per-bot fee totals
and certified fill ids; the merkle log holds a signed `TradeRecord`; the chain
holds the commitment arguments. No file on disk carries the old record shape, and
the five added fields all have defaults, which leaves every existing construction
valid.

### Where each part of an activation comes from

```
exchange_id    the bot's own config field of that name, 'coinbase' on all 38
season         LocalTestnet.get_competition_stats() current_season, which reads 1
symbol         the fill's own symbol
the pool       Activation.allotment_for(symbol) inside that exchange and season
ta_timeframe   the bot's own config field of that name, '5m' on all 38
scored_axes    TradeGrade.scored_axes
execution_bps  TradeGrade.execution_bps
fee_usd        absent from every emit site and from the pinned log schema
```

`_current_season` is set to 1 in `LocalRegistry.__init__` and assigned nowhere
else in `src/`. `contracts/CompetitionRegistry.sol:395` holds the only
`advanceSeason`, and nothing in Python calls an equivalent, so every activation
today is season one. Governance is the unit that turns that call into a vote.

## The correction

### The fill names its activation and the socket asks the bounds

Five fields were added to `CertifiedFill`, each named for the `AwardRequest` field
it feeds, so no second spelling of any of them exists. Two properties resolve the
names: `activation` returns `activation_key(exchange_id, season)` and `pool`
returns `pool_key(exchange_id, season, symbol)`.

`CertificationSocket.__init__` takes `capture_bounds`, the same way it takes the
chain and the ledger. `certify` calls `_award_for`, which builds an `AwardRequest`
and calls `CaptureBounds.award` under the shared chain lock. The mint is then
conditional on the reason.

```python
            distilled = (
                self._ledger.distil(self._wallet_for(bot_id), fee, grade)
                if award_reason == AWARDED
                else Decimal(0)
            )
```

A refused fill is still signed, appended to the merkle log, posted to the chain
and counted towards the bot's lifetime certified fee. Unit 7's contract is that
every fill reaches the chain through the socket and that the fee total rises
monotonically; refusing to certify would have broken both for the large majority
of fills, which the cooldown alone refuses.

A socket built with no bounds behaves exactly as before, and
`socket_summary()["awards_bounded"]` reports which of the two it is.

### The order the locks are taken

`_award_for` acquires the chain lock inside the socket's state lock, releases it,
and `_post_commitment` acquires it again afterwards. The bridge's
`_mutation_lock` is a plain `threading.Lock`, so the two acquisitions are
sequential and never nested. No path anywhere takes the chain lock before the
state lock.

### A zero award is refused

```python
        if amount == 0:
            raise CaptureRefusedError(
                NOTHING_TO_AWARD,
                f"a fee of {request.fee_usd} at a grade of {request.grade_numeric} "
                f"distils nothing, and granting it would spend {participant}'s one "
                f"allotment of {symbol} and open a cooldown for no Quintessence",
            )
```

It sits immediately after the amount is computed and before the share ceiling, so
it raises out of `_refusal_for` before `award` writes the take, the draw, the
cooldown or the chain record.

### The emission figure is refused by name

`activate` already took the figure as an argument. A caller with no figure passed
None and got a `TypeError` naming a type. It now refuses with
`EMISSION_NOT_SET` and a sentence naming the open decision, and
`EMISSION_PER_ACTIVATION` is None in the module where a reader would look for a
number, so no default can become the answer.

### The bridge builds the bounds before the socket

`install_on` built the socket first and the bounds third, so the socket could not
be handed them. The rotation and the bounds now install first, and the socket
takes the bounds it was given or the one the bridge holds.

## The rerun

### The award path, constructed by the program

```
CaptureBounds installed (path=<scratch>/live_bounds.json, activations=0,
  cooldown 3 candles floored at 900s, 1 scored axis minimum)
CertificationSocket installed (path=<scratch>/live_socket.json, bots=0,
  awards bounded=True)

socket_summary['awards_bounded'] = True
bounds is the one installed       = True
bounds_summary['emission_per_activation'] = None
```

### The live configuration refuses every real fill at the first bound

```
tickers ingested: 931
eligible        : 6  draw_size 0
refusals        : {'no_genesis_date': 14}

RE/USD sell at 0.459, activation 'coinbase:1', pool 'coinbase:1|RE/USD'
  not_activated: RE/USD holds no Quintessence allotment in coinbase:1, so there
  is no pool for an award to come out of
  award_reason : not_activated
  distilled    : 0 Quintessence
```

### Real fills, against a pool that exists

1,709 entries read from the live trade log, 1,668 graded, 0 carrying a fee. One
participant per case, so each bound answers on its own cause.

```
one scored axis, inside the span
  SOL/USD sell at 68.49   axes 1   bps None    grade 0.0679
  AWARDED   0.06790 Quintessence   drawn 0.06790 of 5902.5851

two axes, past the span
  SOL/USD buy at 64.65    axes 2   bps -560.67  grade 1.0
  AWARDED   1.00 Quintessence      drawn 1.06790

two axes, inside the span
  SOL/USD sell at 69.04   axes 2   bps -80.30   grade 0.5
  AWARDED   0.50 Quintessence      drawn 1.56790
            pool 5902.5851   ceiling 295.1292   cooldown 900s
            tx 0x2fd9488f18d563

one clamped axis
  SOL/USD sell at 106.4953  axes 1   bps -646.34  grade 1.0
  REFUSED   sole_axis_clamped
  this grade scored execution and nothing else, and its reference price sits
  -646.3 basis points from the fill, past the 100 the axis reads; a reference
  that far out is stale, so the one axis reports a clamp and the grade of 1.0
  rests on nothing

the same market, the same participant, a second time
  allotment_taken: already took an allotment of TAO/USD in coinbase:1; one
  allotment a participant a market an activation period
```

### The fee gap, one fill driven twice

```
SUI/USD sell at 0.8223, two axes, grade 1.0

fee 0.0   nothing_to_award   0 Quintessence
          a fee of 0.0 at a grade of 1.0 distils nothing, and granting it would
          spend 0x364cf213...'s one allotment of SUI/USD and open a cooldown for
          no Quintessence

fee 1.0   awarded            1.00 Quintessence
          pool 817.1556   ceiling 40.8577   drawn 1.00   cooldown 900s
          tx 0x867d945102fd2e
```

### A fill naming no activation

```
RE/USD sell at 0.459, exchange_id '', season None
  activation=''  pool=''
  fill ...:bare on RE/USD names no activation, so no market pool pays it
  award_reason : no_activation_named
  distilled    : 0 Quintessence
```

### The emission figure nobody set

```
emission_not_set: no emission was named for this activation, and no figure here
sets how much Quintessence a market's pool holds in a window; activate takes it
as an argument and no default stands in
```

### Demo mode

One class, two chains, the same `certify` path, no flag.

```
the same class        : CertificationSocket and CertificationSocket
the same chain object : False
demo activation       : coinbase:1

PUMP/USD sell at 0.0045224, axes 2, grade 1.0
  AWARDED  1.00 Quintessence
  pool 964.6291  ceiling 48.2314  cooldown 900s  tx 0x19cb1fbfba07fc

live chain   4 CaptureBounds records
demo chain   1 CaptureBounds record
```

### Nothing was written under the runtime tree

Fifteen files, all under the scratch folder: two chains, two ledgers, four
bounds and rotation records, four sockets and the driven identities.

## What this does not reach

`CertificationSocket.attach_to_bus` has no caller anywhere in `src/` or in
`main.py`. The socket is constructed on every launch and nothing subscribes it to
`trade.filled`, so no real trade reaches `certify` while the platform runs.
Wiring it would start minting against the live `QuintessenceLedger` on every fill,
which decides what a figure the operator reads means rather than repairing a
defect, so it is named here and on the manual page.

The per-fill venue fee is the other half. The venue reports it, and
`src/exchange/position_health.py:90` already sums it per bot into
`BotStats.fees_paid_exchange`, which the status screen shows. No emit site and no
log field carries the individual fill's fee, so every certified fill built from
the bus payload distils nothing and the `nothing_to_award` bound now says which
number is missing rather than spending the allotment for it.

## Archetypes

```
src/competition/certification_socket.py   coding passed=True   ta passed=True
src/competition/capture_bounds.py         coding passed=True   ta passed=True
src/competition/__init__.py               coding passed=True
src/gui/shared_testnet.py                 coding passed=True   gui passed=True
                                                               ta passed=True
docs/manual/08-tabs/proof-of-accumulation.md   docs passed=True
tests/debug_reports/2026-09-10_unit27_certify_activation.md   docs passed=True
```

The fixture pair was driven once this session: `known_good.py` exit 0
`passed=True`, `known_bad.py` exit 1 `passed=False` with 22 findings, so the
instrument discriminates.

```
python -m tools.local_ci --lane black    VERDICT: PASSED
python -m tools.local_ci --lane flake8   VERDICT: PASSED
```
