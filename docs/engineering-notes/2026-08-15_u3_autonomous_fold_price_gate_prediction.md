# U3 prediction: which autonomous folds stop, and which must not

Registered 2026-08-15, BEFORE the change ships. Unit U3, island
`ISLAND_U3GATE2`, against `v3.25.6` at git `5405996436d1`. Nothing is
promoted and no version is bumped.

An island proof is a hypothesis about a running system. Every number
below is a prediction that a real launch can falsify. Each row names a
bot, a trigger price and an expected refusal, so the operator can check
it against his own ladder.

## What changes

`_execute_manual_rebalance` is reached by three callers. Two fire with
no operator present: Wire Stack and Max Cartridge. On that path every
MEM-171 gate is bypassed by design, and nothing compared the rebuy price
against the price the tranche was sold at.

The change adds one refusal on the FOLD side, for those two callers
only. The rule is not new. It is the autonomous tick fold-back's own
per-tranche filter, asked through the same module:

    eligible  <=>  price <= ref * fold_rebuy_factor(interval, fee)

The whole fire is withheld when NOT ONE queued tranche is eligible.

## What does NOT change

- The operator's own button. `manual_button` is exempt.
- The SCRUM side of the same method. It sells and still does.
- A fold on a bot with an empty ladder. No `ref` exists to measure
  against, so nothing is refused.
- A fold where SOME tranches are eligible. It fires, unchanged.

## Prediction 1: two bots, two refusals

Measured read-only from `~/.acervator/bot_state.json`, 37 bots, saved
`2026-08-15 04:15:14`. Each bot was driven through the real
`_execute_manual_rebalance` at the price where ITS OWN Max Cartridge
FOLD arms:

    P_fire = target * (1 - max_cartridge_size_pct/100) / (holdings * qrate)

| bot | symbol | arms at | tranches | admits up to | must fall | withheld |
|---|---|---|---|---|---|---|
| `5ca99f1f` | KAT/USD | 0.00411874 | 10 | 0.00410960 | 0.222 % | $10.14 |
| `f7295d86` | TAO/USD | 191.01840233 | 25 | 187.93535584 | 1.614 % | $3.97 |

Total: 2 bots, $14.11 per fire.

Both run interval 5.0 % and fee 1.6 %, so the factor is 0.9340. KAT's
ladder is ten tranches all at ref 0.00440000. TAO's runs from ref
189.34000000 to 201.21558442, and even its dearest ref does not admit
the arming price.

KAT is the near miss worth watching. It is refused by 0.222 %. A small
move in either direction flips it.

### Two numbers, and why they differ

The refusal line says `$10.06 withheld` for KAT. The table says $10.14.
Both are right and they measure different things:

- **$10.06** is `abs(delta_usd)`, the deficit before compound growth.
  The emit reports it because that is the figure the operator sees in
  the fold's own sizing message.
- **$10.14** is the order the pre-change code actually placed. It is
  larger because the fold sizes against the POST-growth target.

The honest "money stopped" figure is $10.14 for KAT and $3.97 for TAO.

## Prediction 2: 35 bots keep firing, byte for byte

The same 37 bots were driven through both the shipping method and a
provably pre-change twin, at two prices and three caller intents: 216
runs in all.

| intent | refused | still placed | no-op | identical |
|---|---|---|---|---|
| `max_cartridge` | 2 | 35 | 35 | all |
| `wire_stack` | 2 | 35 | 35 | all |
| `manual_button` | 0 | 37 | 35 | all |

107 fires still place an order. All 107 are identical to the pre-change
code at the order call — same symbol, same side, same order type, same
amount, same price argument — and in every mark left on the bot
afterwards: the ladder, the lots, holdings, target, the queue total, the
lifetime-closed counter, trade counts and the emitted messages.

Zero fires raise under the gate that did not raise before.

**`manual_button` places 37 where the autonomous intents place 35.** The
difference is exactly KAT and TAO. The operator can still fire both by
hand.

## The falsifier

This prediction is wrong if, on a real launch:

1. A bot other than `5ca99f1f` or `f7295d86` logs
   `AUTONOMOUS FIRE REFUSED (opposing distance)` while its ladder holds
   a tranche the price clears; or
2. KAT or TAO fires a Max Cartridge or Wire Stack FOLD at or above the
   prices above without that line appearing; or
3. A `MANUAL_FOLD` is refused with that line; or
4. Any `CARTRIDGE_SCRUM`, `WIRE_STACK_SCRUM` or `MANUAL_SCRUM` is
   refused with it. The gate sits inside the FOLD branch and cannot
   reach a sell.

Item 4 is the one that would cost money in the wrong direction.

## What bounds these numbers

**Price provenance.** No live ticker is reachable read-only and none was
fetched. Two prices are used, and both are named in the raw output:
`fire`, solved from each bot's own cartridge config, and `now`, the
bot's `last_trade_price`.

**At `now`, nothing is refused, and that zero is an artefact.** With
price taken from the bot's own last trade, `current_value` is close to
`target_balance` by construction, so every bot lands in the dust band
and no fold fires at all. All 70 autonomous runs at `now` are no-ops on
both the old code and the new. That zero is a statement about the proxy,
not about the world, and it is not evidence the gate is inert.

**Wallet.** Each bot was given an unconstrained quote balance. A
withheld amount is therefore the buy the bot INTENDED before clipping.
The real wallet can only make it smaller.

**The ladder moves.** The state file is rewritten by the running
application; it changed four times during this measurement. The refused
set is a property of the ladder at the timestamp above.

## What this change does NOT close

The order is placed BEFORE the discharge loop runs. When SOME tranches
are eligible, the fire therefore proceeds and the loop still walks into
ineligible ones. It sorts by `ref` descending and consumes until the
fill is exhausted. Those units are rebought, book no profit, and their
queued dollars leave the ladder.

That residue is real. It is a different verb: it moves where bought
units land rather than stopping a trade, and it needs its own change.
This unit does not fix it and must not be read as having done so.

## Prior record, corrected

The carried record said 461 tranches, $208.16, 23 bots. That was an
upper bound on tranches the gate WOULD refuse if a buy ever reached
them. Most never will, because a cartridge FOLD arms on a price DROP and
a drop makes most tranches eligible. Measured at the prices where the
fires actually happen, the answer is 2 bots and $14.11.

The record also named the wrong path. The path a reader would call "the
autonomous fold" — the tick fold-back — has been gated since v3.16.43.
The ungated executor is the one Wire Stack and Max Cartridge share.
