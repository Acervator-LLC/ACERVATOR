# Issue #106 -- the per-Fold growth cap compounds

fleet anchor $3,501.51 -> target $3,593.75; parked $13.37; cap percentages in use [1.0]

rows measured: 228  (bots 38, tape lengths 6, assets with no tablet: 0 [])

## Value sweep

```
digest BEFORE  a7b0253772beb13ec3b9718d7447fb6b4ebb3544a0fc05ca0c4c100f9df7dd31
digest AFTER   ca0b6ff8e291b932ea33929e92dd8b53fe793e2847a85b1177db5c8b75a7b6e7
```

**210 of 228 rows move.**

### the cap the moment this ships

| bot | anchor | target | consumed | cap before | cap after | delta | parked |
|---|---|---|---|---|---|---|---|
| IMU | $50.00 | $63.53 | $0.0000 | $0.5000 | $0.6353 | $+0.1353 | $1.34 |
| CHIP | $251.51 | $260.73 | $0.0000 | $2.5151 | $2.6073 | $+0.0922 | $0.00 |
| ALLO | $125.00 | $133.10 | $0.2390 | $1.2500 | $1.3286 | $+0.0786 | $0.00 |
| BILL | $300.00 | $307.65 | $0.0000 | $3.0000 | $3.0765 | $+0.0765 | $0.00 |
| BICO | $50.00 | $55.95 | $0.0000 | $0.5000 | $0.5595 | $+0.0595 | $0.72 |
| CAP | $50.00 | $55.41 | $0.5000 | $0.5000 | $0.5491 | $+0.0491 | $7.79 |
| RE | $50.00 | $54.19 | $0.0000 | $0.5000 | $0.5419 | $+0.0419 | $0.00 |
| BIO | $100.00 | $103.98 | $0.0000 | $1.0000 | $1.0398 | $+0.0398 | $2.53 |
| SPK | $200.00 | $203.51 | $0.0000 | $2.0000 | $2.0351 | $+0.0351 | $0.00 |
| GROVE | $100.00 | $103.10 | $0.0000 | $1.0000 | $1.0310 | $+0.0310 | $0.00 |
| PENGU | $100.00 | $102.75 | $0.0000 | $1.0000 | $1.0275 | $+0.0275 | $0.09 |
| KAT | $200.00 | $202.71 | $0.0000 | $2.0000 | $2.0271 | $+0.0271 | $0.00 |

Fleet per-cycle cap: **$35.0151 -> $35.9301**, a change of **$+0.9150** (+2.61%).

### the trajectory, per tape length

| bars | rows | median cycles | fleet target after N (before) | (after) | difference |
|---|---|---|---|---|---|
| 35 | 38 | 0 | $3,599.50 | $3,599.79 | $+0.29 |
| 40 | 38 | 0 | $3,606.00 | $3,606.42 | $+0.42 |
| 60 | 38 | 1 | $3,633.50 | $3,635.15 | $+1.65 |
| 100 | 38 | 3 | $3,703.28 | $3,707.76 | $+4.47 |
| 200 | 38 | 8 | $3,859.09 | $3,875.74 | $+16.64 |
| 400 | 38 | 17 | $4,182.26 | $4,250.35 | $+68.09 |

Each row runs its own bot's live target forward by the number of D2-b cycles its own asset's tape contains. The BEFORE column adds a constant `anchor * pct/100` every cycle; the AFTER column adds `pct/100` of the target it has reached. The gap is the curve the operator asked for.

## Calibration

### C0 the decision instrument is the production packer

`_plan_fold_consumption` self-attributes touched: `[]`

Empty is what makes the unbound call legitimate. A non-empty list would mean every admission verdict below came from a stub.

### C1 instrument control -- the reader is not blind

| question | count |
|---|---|
| bots declared in state | 38 |
| bots read | 38 |
| bots with `target != anchor` | 35 |
| bots with a queued tranche ladder | 37 |
| tablets read | 406 |
| rows measured | 228 |

A zero on the third line would have meant a blind reader rather than a healthy fleet.

### C2 positive control -- injected perturbation, the cap

| injected into pct | rows whose cap moves |
|---|---|
| 0 | 0 |
| 1e-12 | 228 |
| 1e-09 | 228 |
| 1e-06 | 228 |
| 0.001 | 228 |
| 0.01 | 228 |

Zero at zero injection and every row at 0.01 is the instrument saying it can see a change of the size this repair makes. A zero elsewhere in this report is only believable because this line is not zero.

### C3 positive control -- injected perturbation, the packer

| injected into budget (USD) | admission verdicts that move |
|---|---|
| 0 | 0 |
| 1e-09 | 6 |
| 0.001 | 6 |
| 0.01 | 12 |
| 0.1 | 60 |
| 1 | 150 |
| 100 | 222 |

The packer is a step function, so small injections move nothing and that is correct behaviour rather than a dead instrument. The last row proves it is alive.

### C4 the tape actually produces fold cycles

| bars | rows | cycles: min | median | max | rows with zero |
|---|---|---|---|---|---|
| 35 | 38 | 0 | 0 | 2 | 31 |
| 40 | 38 | 0 | 0 | 2 | 25 |
| 60 | 38 | 0 | 1 | 4 | 12 |
| 100 | 38 | 2 | 3 | 5 | 0 |
| 200 | 38 | 5 | 8 | 12 | 0 |
| 400 | 38 | 10 | 17 | 23 | 0 |

N is the exponent in `1.01^N`. All-zero here would mean every trajectory below ran zero cycles and every trajectory delta was zero for a reason that has nothing to do with the repair.

### C5 the change is a no-op where it must be

Rows where the bot has no accrued growth and no consumption booked: **18**. Of those, rows where the cap changed: **0**.

On a bot that has never compounded, `target == anchor` and `consumed == 0`, so the new base IS the anchor and the two caps must be bit-identical. Any row in the second count would mean the repair moved a number it had no business moving.

### C6 is the change one-directional?

| direction | rows |
|---|---|
| cap WIDER after | 210 |
| cap identical | 18 |
| cap NARROWER after | 0 |

STRUCTURALLY, not just observed. `cap_after - cap_before = (target - consumed - anchor) * pct/100`, so the cap widens exactly when accrued growth (`target - anchor`) is at least the consumption booked this cycle. Every dollar of this cycle's consumption was ADDED to the target by the same line that booked it, so accrued growth contains it and the difference cannot be negative. The two states that break the containment are named in the property's docstring: detonation resets the target to the anchor without clearing the consumption, and a withdrawal below the anchor does the same. Both self-clear on the next cycle reset, and detonation is disabled on all 38 live bots.

### calibration verdict: PASSED

## Decision sweep

```
digest BEFORE  e33e71725783b0cb3ecce26a162d680d6689e36bfb5c723b041f0c01c25b1e22
digest AFTER   bb669e36eed31736938685d6b898c6c86dd1841a0b8f8ec2fea7c4259b4d551c
```

Rows carrying a queued tranche ladder: **222**. Rows where the production packer takes a DIFFERENT set of tranches: **30**.

| direction | rows | fold-back USD deployed |
|---|---|---|
| MORE deployed after | 204 | $+5.4799 |
| LESS deployed after | 0 | $+0.0000 |
| unchanged | 18 | $0.0000 |

### every flip, attributable

| bot | ladder | budget before | budget after | taken before | taken after | part before | part after | USD before | USD after |
|---|---|---|---|---|---|---|---|---|---|
| RE | 26 | $0.5000 | $0.5419 | 2 | 3 | 1 | 1 | $0.5000 | $0.5419 |
| PENGU | 89 | $1.0000 | $1.0275 | 6 | 7 | 1 | 1 | $1.0000 | $1.0275 |
| BILL | 230 | $3.0000 | $3.0765 | 126 | 127 | 1 | 1 | $3.0000 | $3.0765 |
| CHIP | 210 | $2.5151 | $2.6073 | 83 | 86 | 1 | 1 | $2.5151 | $2.6073 |
| CAP | 80 | $0.0000 | $0.0491 | 0 | 1 | 0 | 1 | $0.0000 | $0.0491 |

A flip is one direction only, and the reason is structural rather than statistical: `_plan_fold_consumption` is monotone in its budget. It walks the ladder in a fixed order and takes the whole of each tranche that fits, then the remaining room from the next. A larger budget can only take at least as much from each tranche in that order, so no tranche admitted under the smaller budget can be dropped by the larger one. C6 shows the budget itself only moves one way, so the deployment can only move one way too.

WHAT A FLIP IS AND IS NOT. It is a tranche REBUY that the cap used to defer to a later cycle and now admits this cycle. The tranche was already price-eligible: every gate upstream -- TA bearish, BB threshold, the MEM-171 per-tranche price floor -- had already passed it, and the cap was the last thing holding it. Nothing here admits a tranche that a price gate refused.

