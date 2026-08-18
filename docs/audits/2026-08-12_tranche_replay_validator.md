# Current Tranche Validator: the exchange record against the stored tranches

Reference — a reconciliation record. It compares the tranche state derived
by replaying the Coinbase export against the tranche state the bots hold,
and it proposes a change set. Nothing was applied.

**One line:** All 561 stored fold tranches tie to a real exchange sell, and
the replay independently produces the over-cap tranches on CAP and PUMP
rather than contradicting them — so the $93.62 stranded capital is a cap
defect, not bad data, and the repair is not "these should not exist".

| Question | Answer | Basis |
|---|---|---|
| Do stored tranches match the record? | **YES, all 561** | Each ties to an export sell by `created_ts` (median gap 1 s) and by `ref` price. 0 untied. |
| Are the stranded tranches supported? | **YES, 35 of 35** | 22 of 22 on CAP and 13 of 13 on PUMP. The replay makes over-cap tranches at the same sells. |
| Is the store over-committed? | **NO, under-committed** | Record supports $499.39 queued; the bots hold $199.17. |
| Repair or reset? | **REPAIR the cap, not the data** | A reset destroys $136.65 of protection on 474 underwater tranches and fixes nothing the record objects to. |

Date: 2026-08-12. Analysis only. This work changed no product code, applied
no change set, and wrote nothing to `~/.acervator`.

---

## 1. The live state was not touched

`~/.acervator/bot_state.json` was hashed at the start and end of this work.

| Moment | mtime (UTC) | sha256 | Size |
|---|---|---|---|
| Start | 2026-08-12 20:37:25 | `3001aae292347a9c492bdcfd373418aef8687dc163962277fc8ba8e9a1f0a238` | 862,602 |
| End | 2026-08-12 21:00:25 | `dc66cbee92eb3338926eb5c95da2dc074db4de5b7a5aa68e65bb4463399a94c6` | 862,615 |

**The hash CHANGED, and I am reporting that plainly rather than claiming a
clean result.** I did not write the file. The RUNNING APP rewrote it at
21:00:25, 23 minutes into this work, the same way it rewrote it twice
during the two earlier hops. Three things support that:

- No script in `scratchpad/CMP/` opens any path under `~/.acervator`. Every
  write target is `os.path.join(HERE, ...)` or `os.path.join(MUT, ...)`,
  both inside the scratchpad. The only occurrences of the string
  `acervator` in those scripts are docstrings that say the file is never
  opened.
- The pinned copy's sha256 is byte-identical before and after every run:
  `cab0049cd67d4e6598449f3153f969a23b06ffdc064d2a34369686a6ccff0bb1`.
- The file GREW by 13 bytes and its mtime advanced, which is the shape of
  the app's periodic save, not of an analysis.

Anyone re-running this work must expect a different live hash again. That
is the point of the pinned copy.

Every read went to a PINNED COPY taken earlier in the session, at
`scratchpad/GT/bot_state_copy.json`, sha256
`cab0049cd67d4e6598449f3153f969a23b06ffdc064d2a34369686a6ccff0bb1`,
saved 2026-08-12 12:57:25 UTC. The copy holds 561 fold tranches.

**The live file moves on its own.** The running app rewrote it during the
session. The brief cites 652 tranches; the pinned copy holds 561; the live
file has changed size again since. CAP still holds 61 and PUMP still holds
22, so the per-bot figures in the brief are sound, but the fleet total is
not stable. Compute any repair against a pinned copy with the fleet
stopped.

---

## 2. The method, and what it cannot do

### 2.1 What the replay does

The replay walks each bot's exchange fills in time order and runs the
shipping mechanism forward. A SELL consumes main lots highest-cost-first
and spawns one fold tranche per lot slice. A BUY consumes fold tranches and
returns their units to main lots. Whatever stands at the end is the derived
tranche state.

Two consumption rules exist in `src/trading/scrumming_bot.py` and they
disagree. Rule A (`:11253-11298`, manual and cartridge folds) has no price
gate and splits tranches. Rule B (`:9637`, `:9694-9709`, autonomous folds)
gates on price and admits whole tranches only. Rule A is primary here: of
470 buy-side records the app itself labelled, 405 (86.2%) ran Rule A. Rule B
figures are carried alongside.

### 2.2 How a stored tranche is tied to a sell

A stored tranche carries `ref`, the sell price the bot recorded, and
`created_ts`, the moment the bot built it. The export carries a sell price
and a UTC timestamp. A tranche counts as TIED when it matches a sell within
300 seconds AND within 1% on price. Both witnesses are independent.

Measured alignment on the pinned copy: 561 of 561 stored tranches TIED.
Typical gap is 0 to 10 seconds. Typical price error is below 0.1%.

### 2.3 The three limits that bound every number here

1. **`scrum_fold_pct` is honoured at one site only.**
   `src/trading/scrumming_bot.py:8854` applies it, inside the autonomous
   scrum. The manual and cartridge scrum path at `:11005-11027` builds
   tranches with no scaling. Every dollar figure therefore carries a low
   and a high bound. The bound only separates on the 8 bots set to 50.
2. **Smart-wire routing is invisible to the export.**
   `_route_scrum_proceeds_via_wires` (`:1885`) reduces the scrum proceeds
   before tranches are built. The export cannot see an internal transfer,
   so derived tranche dollars are biased HIGH by an amount that cannot be
   sized.
3. **Comparison happens per sell burst, not per tranche.**
   A sell slices across however many lots the bot held. Lot fragmentation
   is internal and the export cannot see it, so tranche COUNTS are not
   comparable. Dollars at one sell burst are.

### 2.4 Attribution confidence

The map is bijective. 37 bots hold 37 distinct `config.target_asset`
values. No asset carries two bots. The only export assets with no bot are
USD and USDC, both cash rail. `mode` is `scrumming` on all 37, so no
Extractor scans alternative targets; `extractor_alt_targets` is empty on
all 37; `profit_route_bot_id` is empty on all 37. The 33 smart wires move
USD, and the receiving bot spends it on its own asset.

**Attribution is CERTAIN on 37 of 37 assets. No asset is ambiguous.**

The residual uncertainty is not "which bot" but "was this fill the app at
all". Operator trades placed directly on Coinbase are byte-identical to bot
fills. LSETH and LTC have exactly that shape: one buy, no sells, one main
lot, no tranche ever created.

### 2.5 Terminal actions

Detonation and self-destruct neither spawn nor consume a tranche. Neither
appears in this record. `detonation_enabled` is False on all 37 bots, and a
recursive search of the retained log tree returns zero hits for
`AUTO_DETONATION`, `SELF_DESTRUCT`, `DETONATION` or `SELF-DESTRUCT`. The
same search over the same tree returns 61,424 hits for `SCRUM`, so the zero
is a measurement and not a blind instrument.

The Coinbase export carries no bot id and no action label, so terminal
actions cannot be distinguished there. **All 1,989 sells were treated as
ordinary Scrums. No threshold was invented.** The exclusion is a no-op on
this data.

---

## 3. Derived against stored, per bot

Ranked by absolute dollar difference. "Unsupported $" is stored capital at
a sell burst where the replay retains nothing. "Missing $" is derived
capital at a burst the store no longer holds. "Derived $ high" is the
`scrum_fold_pct` upper bound from section 2.3.

| Asset | Bot | Stored # | Derived # | Stored $ | Derived $ | Derived $ high | Diff | Unsupported $ | Missing $ |
|---|---|---|---|---|---|---|---|---|---|
| RAVE | a0a82b8c | 12 | 670 | 8.35 | 220.18 | 220.18 | +211.83 | 0.00 | 211.92 |
| ETH | 7c4c4ff3 | 0 | 63 | 0.00 | 35.56 | 35.56 | +35.56 | 0.00 | 35.56 |
| ORCA | 695f39e1 | 0 | 143 | 0.00 | 25.50 | 104.88 | +25.50 | 0.00 | 25.50 |
| CAP | f9cfb7ba | 61 | 119 | 31.24 | 55.81 | 55.81 | +24.57 | 0.00 | 25.31 |
| BIO | 7c30a150 | 1 | 119 | 1.67 | 18.97 | 18.97 | +17.31 | 0.00 | 17.22 |
| CHIP | c8e5c5db | 116 | 127 | 14.33 | 0.00 | 11.62 | -14.33 | 8.72 | 0.00 |
| LINK | 4a53be56 | 29 | 38 | 12.57 | 3.22 | 15.34 | -9.36 | 6.78 | 0.53 |
| XRP | a873b457 | 6 | 0 | 6.04 | 0.00 | 134.87 | -6.04 | 6.04 | 0.00 |
| ZEC | b2ef9a74 | 37 | 55 | 10.96 | 15.14 | 15.14 | +4.18 | 0.00 | 0.05 |
| ALLO | 45e9e720 | 16 | 23 | 14.23 | 18.38 | 18.38 | +4.16 | 0.00 | 5.74 |
| BILL | 95340bda | 0 | 39 | 0.00 | 3.04 | 3.04 | +3.04 | 0.00 | 3.04 |
| AGLD | a632ff52 | 4 | 3 | 5.46 | 3.38 | 3.38 | -2.08 | 2.10 | 0.00 |
| BTC | 7c39c7a2 | 11 | 29 | 3.83 | 1.92 | 3.83 | -1.92 | 0.00 | 0.00 |
| KAT | 5ca99f1f | 68 | 87 | 10.96 | 12.57 | 12.57 | +1.61 | 0.00 | 0.00 |
| TAO | f7295d86 | 25 | 39 | 5.99 | 7.58 | 7.58 | +1.58 | 0.00 | 1.21 |
| ONDO | d9681a57 | 21 | 32 | 4.33 | 5.71 | 5.71 | +1.38 | 0.00 | 0.00 |
| VVV | a8d95fed | 42 | 55 | 7.55 | 8.81 | 8.81 | +1.26 | 0.00 | 0.00 |
| PENGU | 7a0334bb | 33 | 43 | 6.41 | 7.63 | 7.63 | +1.21 | 0.00 | 0.00 |
| SOL | bbe339a0 | 12 | 28 | 2.93 | 1.81 | 12.00 | -1.12 | 0.03 | 0.00 |
| PUMP | 650df31a | 22 | 29 | 26.03 | 26.69 | 26.69 | +0.66 | 0.00 | 1.11 |
| DOGE | a7dbc8ef | 16 | 20 | 2.50 | 3.12 | 3.12 | +0.62 | 0.00 | 0.00 |
| GROVE | 803eb6a8 | 11 | 18 | 3.59 | 3.77 | 3.77 | +0.19 | 0.00 | 0.00 |
| HYPE | e6df7221 | 3 | 3 | 2.06 | 2.23 | 2.23 | +0.17 | 0.00 | 0.00 |
| RE | 04e1cafc | 8 | 18 | 6.10 | 6.24 | 6.24 | +0.15 | 0.00 | 0.00 |
| WLFI | c0d9eb49 | 1 | 1 | 1.49 | 1.57 | 1.57 | +0.08 | 0.00 | 0.00 |
| HBAR | 7a4e0e88 | 1 | 1 | 0.25 | 0.27 | 0.27 | +0.03 | 0.00 | 0.00 |
| ADA | ff6a37a3 | 4 | 5 | 5.24 | 5.24 | 5.24 | -0.00 | 0.00 | 1.01 |
| BICO | 4c4188e8 | 1 | 7 | 5.04 | 5.04 | 5.04 | -0.00 | 0.00 | 0.00 |
| AERO | cc18670d | 0 | 0 | 0.00 | 0.00 | 0.00 | +0.00 | 0.00 | 0.00 |
| BONK | 092428b2 | 0 | 0 | 0.00 | 0.00 | 301.81 | +0.00 | 0.00 | 0.00 |
| IMU | 168b78e3 | 0 | 0 | 0.00 | 0.00 | 0.00 | +0.00 | 0.00 | 0.00 |
| LSETH | 9f1b9bff | 0 | 0 | 0.00 | 0.00 | 0.00 | +0.00 | 0.00 | 0.00 |
| LTC | 934f242d | 0 | 0 | 0.00 | 0.00 | 0.00 | +0.00 | 0.00 | 0.00 |
| NEAR | 9f737e8f | 0 | 0 | 0.00 | 0.00 | 0.00 | +0.00 | 0.00 | 0.00 |
| SPK | ae2f02cf | 0 | 0 | 0.00 | 0.00 | 0.00 | +0.00 | 0.00 | 0.00 |
| SUI | c1f7469a | 0 | 0 | 0.00 | 0.00 | 0.00 | +0.00 | 0.00 | 0.00 |
| XLM | 5d335c96 | 0 | 0 | 0.00 | 0.00 | 0.00 | +0.00 | 0.00 | 0.00 |

**FLEET:** stored 561 tranches / $199.17. Derived 1,814 / $499.39, upper
bound $1,051.29. Stored capital the record does not support: **$23.68**.
Derived capital the store does not hold: **$328.20**. Stored tranches that
tie to no sell at all: **0**.

Read the direction. The record supports MORE queued fold capital than the
bots hold, not less. Only four bots carry any unsupported stored capital:
CHIP $8.72, LINK $6.78, XRP $6.04, AGLD $2.10, SOL $0.03.

### 3.1 The three bots where the record and the store tell different stories

RAVE, BICO and BIO show the reset signature. On these three the live state
matches a null model with NO tranche history better than it matches the
record. RAVE is the clearest: 670 derived tranches against 12 stored, and a
live cost basis that sits almost on the null model's. The derived state on
these three is UNSUPPORTED, not merely uncertain. `bot_state.json` carries
no per-bot reset timestamp, so the reset cannot be dated and no replay
start point can reconcile it.

---

## 4. The stranded tranches: the record supports every one

A tranche larger than the whole per-cycle cap can never be admitted, because
`src/trading/scrumming_bot.py:9700-9707` refuses to split. The cap is
`anchor_target_balance * max_target_growth_pct / 100` (`:9677-9679`).

### 4.1 CAP/USD — cap $0.5000, 22 of 61 over cap, $24.29

Every one of the 22 ties to a real sell, and the replay makes an over-cap
tranche at the same sell.

| # | Stored $ | Tie | Gap s | Ref error | Derived at that sell | Largest derived | Supported |
|---|---|---|---|---|---|---|---|
| 6 | 1.8770 | TIED | 10 | 1.4e-16 | 3 / $4.6744 | $3.2769 | YES |
| 8 | 0.5055 | TIED | 10 | 1.4e-16 | 3 / $4.6744 | $3.2769 | YES |
| 10 | 0.6025 | TIED | 10 | 1.4e-16 | 3 / $4.6744 | $3.2769 | YES |
| 14 | 1.4270 | TIED | 3 | 1.5e-16 | 1 / $2.4507 | $2.4507 | YES |
| 16 | 0.7569 | TIED | 1 | 0.0 | 9 / $5.5810 | $3.4247 | YES |
| 19 | 1.8249 | TIED | 1 | 0.0 | 9 / $5.5810 | $3.4247 | YES |
| 21 | 0.8250 | TIED | 1 | 0.0 | 9 / $5.5810 | $3.4247 | YES |
| 22 | 0.9087 | TIED | 1 | 0.0 | 9 / $5.5810 | $3.4247 | YES |
| 33 | 1.2180 | TIED | 0 | 1.9e-05 | 11 / $3.3625 | $1.2609 | YES |
| 34 | 0.9659 | TIED | 0 | 1.9e-05 | 11 / $3.3625 | $1.2609 | YES |
| 36 | 0.7214 | TIED | 1 | 8.8e-04 | 2 / $1.1074 | $0.9266 | YES |
| 38 | 1.3966 | TIED | 65 | 4.5e-04 | 1 / $1.6162 | $1.6162 | YES |
| 39 | 1.7256 | TIED | 1 | 5.3e-03 | 1 / $1.7844 | $1.7844 | YES |
| 40 | 3.1799 | TIED | 0 | 0.0 | 2 / $3.1678 | $2.0159 | YES |
| 42 | 0.5830 | TIED | 2 | 0.0 | 9 / $5.6408 | $1.6191 | YES |
| 43 | 0.8560 | TIED | 2 | 0.0 | 9 / $5.6408 | $1.6191 | YES |
| 44 | 0.6045 | TIED | 2 | 0.0 | 9 / $5.6408 | $1.6191 | YES |
| 45 | 1.4036 | TIED | 2 | 0.0 | 9 / $5.6408 | $1.6191 | YES |
| 46 | 0.8714 | TIED | 2 | 0.0 | 9 / $5.6408 | $1.6191 | YES |
| 49 | 0.5804 | TIED | 2 | 0.0 | 9 / $5.6408 | $1.6191 | YES |
| 53 | 0.8266 | TIED | 4 | 3.4e-05 | 1 / $1.1132 | $1.1132 | YES |
| 56 | 0.6344 | TIED | 4 | 3.4e-05 | 1 / $1.1132 | $1.1132 | YES |

**22 of 22 supported. 0 unsupported.**

### 4.2 PUMP/USD — cap $0.5000, 13 of 22 over cap, $23.79

| # | Stored $ | Tie | Gap s | Ref error | Derived at that sell | Largest derived | Supported |
|---|---|---|---|---|---|---|---|
| 0 | 1.0649 | TIED | 2 | 1.3e-03 | 1 / $1.1063 | $1.1063 | YES |
| 1 | 2.3065 | TIED | 1 | 4.5e-04 | 4 / $1.5147 | $0.9350 | YES |
| 3 | 2.6612 | TIED | 1 | 1.4e-03 | 1 / $2.7375 | $2.7375 | YES |
| 4 | 1.2709 | TIED | 1 | 5.0e-04 | 1 / $1.3480 | $1.3480 | YES |
| 5 | 2.8690 | TIED | 0 | 5.0e-04 | 1 / $2.8665 | $2.8665 | YES |
| 6 | 4.6670 | TIED | 0 | 7.9e-07 | 1 / $4.7376 | $4.7376 | YES |
| 7 | 1.4109 | TIED | 1 | 4.1e-04 | 4 / $3.2454 | $1.1620 | YES |
| 8 | 0.9121 | TIED | 1 | 4.1e-04 | 4 / $3.2454 | $1.1620 | YES |
| 9 | 0.9253 | TIED | 1 | 4.1e-04 | 4 / $3.2454 | $1.1620 | YES |
| 11 | 2.3141 | TIED | 248 | 1.6e-06 | 4 / $2.5642 | $1.1187 | YES |
| 16 | 0.8602 | TIED | 1 | 3.7e-04 | 7 / $2.5604 | $0.6300 | YES |
| 19 | 1.5243 | TIED | 1 | 1.4e-03 | 3 / $2.9004 | $1.3140 | YES |
| 21 | 1.0045 | TIED | 1 | 1.4e-03 | 3 / $2.9004 | $1.3140 | YES |

**13 of 22 over cap. 13 of 13 supported. 0 unsupported.**

### 4.3 What this changes

The brief asked what happens if the record does not support these tranches.
It does support them, so that branch does not open. It is worse than that
for the cap: fleet-wide, 72 stored tranches ($105.76) exceed their bot's
whole cycle cap, and the same measure on the DERIVED state gives **$284.21**.
The record produces more unadmittable tranches than the store holds.

The collision is structural. A $50-anchor bot at 1% growth has a $0.50 cap.
The same bot's own scrums routinely spawn $1 to $4.74 tranches, because
spawn size is a fraction of the sale (`:8805-8811`) while admission size is
1% of the anchor (`:9700-9707`). The two numbers were never reconciled. The
repair belongs in the admission rule, not in the data.

---

## 5. The over-allocation ratio, computed from the record

The metric is the one the 2026-08-11 audit used:
`(position_value + queued fold usd) / target_balance`. The derived ratio
replaces both numerator terms with record-derived values, and marks derived
units at the SAME price the stored figure used, so the two differ only by
units and queued dollars, never by price.

**FLEET: stored 1.0473x. From the record, 1.1358x.**

Stored numerator $3,611.76. Record numerator $3,916.81. Common denominator
$3,448.65.

The record says the fleet is MORE over-allocated than the books say, not
less. The books under-report the commitment.

Where the two disagree most:

| Asset | Target $ | Books ratio | Record ratio | Delta |
|---|---|---|---|---|
| RAVE | 50.93 | 1.118 | 5.278 | +4.160 |
| ORCA | 50.47 | 0.994 | 1.499 | +0.505 |
| CAP | 55.41 | 1.518 | 1.961 | +0.443 |
| ETH | 200.38 | 1.001 | 1.179 | +0.177 |
| BIO | 102.84 | 0.958 | 1.126 | +0.168 |
| LINK | 75.22 | 1.179 | 1.054 | -0.124 |
| XRP | 75.77 | 1.068 | 0.989 | -0.079 |
| CHIP | 253.44 | 1.073 | 1.019 | -0.054 |
| AGLD | 50.47 | 1.123 | 1.082 | -0.041 |

Three cautions on this table. RAVE's +4.160 is not a real over-allocation:
RAVE is a reset-signature bot, so its derived ratio is built from a history
the bot does not appear to have lived. The five negative deltas are the
bots whose stored queue exceeds what the record supports. And 24 of 37 bots
agree within 0.05, so the disagreement is concentrated, not general.

The prior audit reported 1.060 fleet-wide on its own snapshot and could not
reproduce an earlier 1.28x figure. This work gives 1.0473x from the books on
the 12:57 snapshot, which is consistent. **1.28x still does not reproduce
from either source.**

---

## 6. The proposed change set

Data only. Nothing here was applied. Full record at
`scratchpad/CMP/changeset.json`, field `"applied": false`.

| Action | Bots | Meaning |
|---|---|---|
| KEEP | 20 | Derived and stored agree, or the store holds LESS than the record supports. No edit. |
| CAP_POLICY | 14 | Stored tranches exceed the whole cycle cap AND the record supports them. The change belongs in code. |
| HOLD | 3 | RAVE, BICO, BIO. Reset signature. The record cannot rewrite these. |
| TRIM | 0 | No stored tranche holds dollars the record refuses. |

**13 of 37 bots need UNITS_REVIEW before any tranche edit.** Their main-lot
units disagree with the export by more than 1%.

| Asset | Stored units | Export units | Delta |
|---|---|---|---|
| CAP | 1136.22765791 | 995.00000000 | +14.19% |
| ORCA | 54.05340782 | 48.73000000 | +10.92% |
| WLFI | 443.89811321 | 458.90000000 | -3.27% |
| LINK | 8.98871905 | 8.72000000 | +3.08% |
| KAT | 45082.77875379 | 43880.00000000 | +2.74% |
| ZEC | 0.31483603 | 0.30660493 | +2.68% |
| BICO | 1525.55515139 | 1563.16000000 | -2.41% |
| PENGU | 16204.55171539 | 15872.00000000 | +2.10% |
| DOGE | 1452.36247531 | 1424.60000000 | +1.95% |
| BONK | 44634697.33848215 | 43884239.00000000 | +1.71% |
| ETH | 0.10861369 | 0.10694096 | +1.56% |
| XLM | 314.75451450 | 310.54673230 | +1.35% |
| BTC | 0.00393965 | 0.00389584 | +1.12% |

CAP is both the worst unit divergence and the bot carrying the most
stranded capital. A tranche repair computed against units that do not exist
is wrong however good the derivation is. **Settle the units first.**

### 6.1 The code changes the data implies

These are findings with file and line. No code was changed.

**F1 — the cap cannot admit what the spawn creates.**
`src/trading/scrumming_bot.py:9700-9707` admits whole tranches only, under
a cap of `anchor * max_target_growth_pct / 100`. `:8805-8811` sizes a
spawned tranche as a fraction of the sale. On a $50-anchor bot at 1%, the
cap is $0.50 and the spawns reach $4.74. 72 tranches fleet-wide can never
be admitted at any price.

**F2 — `scrum_fold_pct` is honoured at one site only.**
`:8854` applies it. `:11005-11027` and `:11770` do not. 270 of 387 labelled
sells took an unscaled path. The fleet fold queue moves from $499.39 to
$1,051.29 depending on which reading is true.

**F3 — two consumption rules in one file.**
`:9637` gates on price and caps; `:11253` does neither and splits. 86.2% of
labelled buys take the ungated one, so the price gate and the cycle cap
govern about 13% of real folds.

**F4 — the sell path never reads back the executed quantity.**
`_execute_sell` (`:12280-12283`) returns `Optional[float]`, a fill PRICE.
`:8785` computes `scrum_usd = scrum_asset * sell_fill` from the REQUESTED
size, and `:8805-8811` debits lots by the requested amount. A truncated or
partial fill leaves the books claiming units the exchange did not sell.
Measured: 17 stored tranche bursts across 12 bots hold slightly more units
than the matching sale sold, and 11 of the 13 unit divergences above are
positive.

**F5 — a tranche can be consumed to nothing and still exist.**
`:11297` removes a tranche only when `units <= 1e-12`. The replay produces
204 such records fleet-wide.

---

## 7. Repair against reset

The operator named both. Here is what each moves.

| Option | Position | Queued fold | Ratio |
|---|---|---|---|
| Fleet now | $3,412.59 | $199.17 | 1.0473x |
| From the record | $3,417.42 | $499.39 | 1.1358x |
| After a reset | $3,412.59 | $0.00 | 0.9895x |

A reset clears the fold queue. It does not touch the position.

**What a reset destroys.** 561 tranches and $199.17 of queued fold capital.
474 of those tranches (84%), holding $136.65, carry an `initial_buy_price`
ABOVE the current price. Those are the underwater lots MEM-171 exists to
protect. Cost-basis provenance is not reconstructable after a clear.

**What a rebuild from the record would put back.** 1,814 tranches and
$499.39, upper bound $1,051.29. But 796 of those tranches ($244.19) sit on
RAVE, BICO and BIO, the three reset-signature bots. A rebuild writes them
from a history the bot does not appear to have lived.

**The case for repair.** The record does not object to the stored tranches.
All 561 tie to real sells. Only $23.68 of stored capital lacks record
support, across five bots. The stranded $105.76 is stranded by an admission
rule, and a reset does not repair that rule — the same bots will rebuild
the same unadmittable tranches from their next scrums. A reset trades
$136.65 of live downside protection for a ratio improvement of 0.058x.

**The case for reset.** It is the only option that needs no unit
reconciliation, and it makes the three reset-signature bots consistent with
the rest. If the operator does not intend to change the cap rule, the queue
will keep growing and a reset only defers the same decision.

**The recommendation, stated as a recommendation and not a fact.** Repair
the cap rule first, settle the 13 unit divergences second, and leave the
tranche data alone. The data is not what is broken.

---

## 8. Proof that the comparison can fail

Every clean number above is reported beside a planted defect that moves it.
Every mutation was written to a COPY under `scratchpad/CMP/mutants/`. The
pinned state copy was hashed before and after: identical, sha256
`cab0049c...`. Verdicts are read against the BASELINE finding set (33
findings), not against zero, because the real state already trips checks.

| Control | Planted | New findings | Named check | Verdict |
|---|---|---|---|---|
| Negative control | nothing; untouched copy | 0 | — | PASS (identical) |
| Inflated tranche usd | CAP tranche 40 usd x10 | 1 | CEILING | DETECTED |
| Fabricated ref | PUMP tranche 6 ref x3 | 1 | TIE | DETECTED |
| Fabricated timestamp | ZEC tranche 0 `created_ts` +30d | 1 | TIE | DETECTED |
| Duplicated tranche | KAT tranche 0 copied | 1 | DUP | DETECTED |
| Unsupported lot | TAO main lots +25% units | 1 | LOTS | DETECTED |

All six held. The exact messages:

- `CEILING CAP MATERIAL burst 6: stored $31.7994 > sale $3.1678`
- `TIE PUMP tranche 6 verdict TIME_ONLY ref_err 0.667`
- `TIE ZEC tranche 0 verdict UNTIED gap_s 1756222`
- `DUP KAT tranche 68 identical to 0`
- `LOTS TAO stored 0.46887162 vs export 0.37480000 (+25.10%)`

### 8.1 What the checks CANNOT catch

A control that fires at 10x says nothing about 1.05x. Both were measured.

| Probe | Result |
|---|---|
| usd inflation on a burst already at its ceiling | CEILING fires from 1.01x |
| usd inflation on a burst with headroom | CEILING needs **50x** |
| duplicate written with a fresh timestamp | DUP MISSES it |
| a tranche DELETED from the store | every check MISSES it |
| fabricated `initial_buy_price` | every check MISSES it |

The ceiling check is strong only where a burst already sits near its
ceiling. On a burst with headroom it is nearly blind.

The second instrument catches what the checks miss:

| Miss | Caught by | Number |
|---|---|---|
| Deleted tranche ($0.7378) | Section 3 table | ZEC diff +4.1796 to +4.9174 |
| Retimed duplicate | Section 3 table | KAT diff +1.6137 to +1.4713 |
| Fabricated cost basis | cost-basis comparison | ZEC basis 537.09 to 571.29, +6.37% |

### 8.2 The control that changed a conclusion

The first run of the ceiling check reported one MATERIAL breach: CHIP, a
burst on 2026-08-12 11:12:38 holding $6.5458 against a $5.7836 sale. The
change set carried a TRIM_TO_SALE action for it.

That was my instrument, not the state. `apply_wire_income`
(`src/trading/scrumming_bot.py:2215-2219`) distributes smart-wire income
evenly across every standing tranche, adding dollars and no units. Those
dollars come from another bot, so the export cannot see them. The tranches
record the provenance in `wire_credits`, and that burst's recorded wire
credits total **$0.7622 — exactly the excess**.

The check now subtracts recorded wire credits. MATERIAL breaches fleet-wide
went from 1 to **0**, and the TRIM action disappeared from the change set.
The three surviving MARGINAL breaches total $0.069 and are consistent with
F4.

### 8.3 The replay engine was not modified

The comparison adds a spawn tag to each derived tranche. A tag must not
change the mechanism. Verified by composition, not by inspection: the
tagged run reproduces the prior hop's `RP/base.json` on all 37 assets with
0 drift in count, dollars and units.

The prior hop's own holdings control passed on 37 of 37 bots and is
reported here with its measured weakness: it stays green through a 250x
oversizing error and only fires at 500x. It confirms the walk's arithmetic
and nothing more.

---

## 9. What could not be determined

1. **Which consumption rule applied to which fill.** Rule A gives 1,814
   standing tranches / $499.39. Rule B gives 2,373 / $3,381.78. The fleet
   mix is known (86.2% Rule A on the buy side); the per-fill assignment is
   not. `trade.log` labels 883 of 4,889 fills and starts 2026-06-09.
2. **The `scrum_fold_pct` bound.** $499.39 against $1,051.29 on the same
   input. Affects the 8 bots set to 50. XRP is starkest: $0.00 under one
   reading, $134.87 under the other.
3. **Smart-wire routing out of scrum proceeds.** Direction of the bias is
   known (derived dollars biased HIGH). The magnitude is not sizeable from
   the export.
4. **When each bot was reset.** RAVE, BICO and BIO carry the signature.
   `bot_state.json` holds no per-bot reset timestamp.
5. **Which fills were terminal actions before 2026-06-09.** No
   action-labelled record exists for the first 58 days. Two full-position
   exits have the shape — CHIP 2026-04-23 and RAVE 2026-06-27 — and are
   reported as a shape, not a classification.
6. **Whether any fill was placed outside the app.** LSETH and LTC have the
   manual-seeding shape. It cannot be proved.
7. **Why 13 bots' units diverge.** Dust accumulation, wire-credited units
   and reset survivors cannot be separated read-only. F4 is a measured
   contributor but not proved sufficient.
8. **The source of the tranche lifetime gap.** `:11819` asserts
   `created - closed - discarded = standing`. The fleet gives 12,267 −
   11,298 − 360 = 609 against 561 standing. The gap runs in both
   directions across 13 bots, so the counters cannot validate the list.

---

## 10. Where the evidence lives

All derivatives are under
`scratchpad/CMP/`: `cmp_core.py` (comparison), `checks.py` (named checks),
`cmp_report.py` (sections 3 to 5), `plant.py` (section 8), `power.py` and
`power2.py` (section 8.1), `changeset.py` (section 6),
`repair_vs_reset.py` (section 7), `equiv.py` (section 8.3).

Outputs: `cmp.txt`, `cmp.json`, `plant.txt`, `plant.json`, `power.txt`,
`power2.txt`, `changeset.txt`, `changeset.json`, `rr.txt`, `equiv.txt`.

Every script cleared `tools.harness.coding_archetype` with `passed=True`
and no high or critical findings. Two drafts failed the gate first; the
code changed, not the gate.

---

## 11. Scope confirmation

- `~/.acervator/bot_state.json` was never opened for writing.
- Nothing was written to `~/.acervator` or `~/.acervator_logs`.
- `coinbase_credentials.json` was never opened.
- No product code changed. No commit, no push, no version bump.
- The source CSV is unmodified.
- No change set was applied.

The live state file is NOT byte-identical between the start and the end of
this work. Section 1 gives both hashes and the evidence that the running
app made that change, not this analysis. The pinned copy this work read is
byte-identical throughout.
