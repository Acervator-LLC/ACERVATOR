# MEASUREMENT — fold-tranche compounding across the live fleet

**Taken** 2026-08-06 from `~/.acervator/bot_state.json`, read-only.
**Prompted by** operator: "See RAVE's YTD history for many examples of this."

This is the evidence table for the tranche-lifecycle repair. It is a
measurement of persisted state, not an inference from code.

## The one number

**10,197 fold tranches have closed. Total lifetime target-balance growth
across the entire fleet is $26.20.**

Combined anchor target $3,300.00 → combined current target $3,326.20.
That is **0.794%** of base, or **$0.00257 per closed tranche**, over the
platform's whole history.

Operator's wording, and it is the accurate one: *compounding has never
functioned globally.* This is not a per-bot defect. It is the whole
fleet, every symbol, every exchange, for the platform's entire run.

## Headline

- **10,197 fold tranches have CLOSED** across 35 bots (11,171 created).
- Total target-balance growth from all of it: **$26.20**.
- Bots whose target never moved off its anchor: **9 of 35**.
- Bots where the max-growth cap ever consumed anything: **3 of 35** (values 0.34, 0.50, 0.09).
- Stranded in `pending_wire_credits`: **$565.8810**. Parked in `standing_surplus_usd`: $1.0992.

The operator's stated symptom is that tranches fill, the target balance
does not rise, and the max-target-growth surplus cutoff therefore never
engages because there is no change to cap. Every column below is
consistent with that and none contradicts it.

## Per bot

| Symbol | bot | trades | closed | created | standing | target | anchor | growth | growth % | cap used | max_growth_pct | pending | surplus |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| CHIP/USD | `c8e5c5db` | 358 | 2880 | 3079 | 178 | 251.77 | 250.00 | +1.77 | +0.71% | 0.00 | 1.00 | 0.0000 | 0.00 |
| BILL/USD | `95340bda` | 421 | 2443 | 2616 | 165 | 253.10 | 250.00 | +3.10 | +1.24% | 0.00 | 1.00 | 0.0000 | 0.00 |
| KAT/USD | `5ca99f1f` | 206 | 709 | 784 | 62 | 200.59 | 200.00 | +0.59 | +0.29% | 0.00 | 1.00 | 0.0000 | 0.00 |
| ALLO/USDC | `45e9e720` | 258 | 574 | 582 | 8 | 126.96 | 125.00 | +1.96 | +1.57% | 0.00 | 1.00 | 0.0000 | 0.00 |
| SPK/USD | `ae2f02cf` | 179 | 526 | 528 | 0 | 200.76 | 200.00 | +0.76 | +0.38% | 0.00 | 1.00 | 0.0000 | 0.00 |
| ORCA/USD | `695f39e1` | 176 | 497 | 628 | 107 | 50.25 | 50.00 | +0.25 | +0.51% | 0.00 | 1.00 | 1.1988 | 0.00 |
| ZEC/USD | `b2ef9a74` | 230 | 412 | 443 | 42 | 150.00 | 150.00 | +0.00 | +0.00% | 0.00 | 1.00 | 0.0000 | 0.00 |
| VVV/USD | `a8d95fed` | 134 | 357 | 376 | 17 | 76.21 | 75.00 | +1.21 | +1.62% | 0.00 | 1.00 | 0.0000 | 0.00 |
| PENGU/USD | `7a0334bb` | 128 | 299 | 311 | 12 | 100.23 | 100.00 | +0.23 | +0.23% | 0.00 | 1.00 | 0.0000 | 0.00 |
| BONK/USD | `092428b2` | 165 | 183 | 194 | 11 | 100.31 | 100.00 | +0.31 | +0.31% | 0.00 | 1.00 | 0.0000 | 0.00 |
| BIO/USD | `7c30a150` | 203 | 147 | 266 | 126 | 102.00 | 100.00 | +2.00 | +2.00% | 0.00 | 1.00 | 0.0000 | 0.63 |
| TAO/USD | `f7295d86` | 108 | 143 | 165 | 22 | 75.35 | 75.00 | +0.35 | +0.47% | 0.00 | 1.00 | 0.0000 | 0.00 |
| ONDO/USD | `d9681a57` | 106 | 129 | 168 | 38 | 75.72 | 75.00 | +0.72 | +0.96% | 0.00 | 1.00 | 0.0000 | 0.00 |
| SUI/USD | `c1f7469a` | 60 | 120 | 121 | 0 | 100.34 | 100.00 | +0.34 | +0.34% | 0.34 | 1.00 | 0.0000 | 0.00 |
| CAP/USD | `f9cfb7ba` | 95 | 114 | 126 | 12 | 55.41 | 50.00 | +5.41 | +10.83% | 0.50 | 1.00 | 0.0000 | 0.47 |
| DOGE/USD | `a7dbc8ef` | 69 | 107 | 123 | 16 | 100.32 | 100.00 | +0.32 | +0.32% | 0.00 | 1.00 | 0.0000 | 0.00 |
| GROVE/USD | `803eb6a8` | 50 | 106 | 106 | 0 | 102.61 | 100.00 | +2.61 | +2.61% | 0.00 | 1.00 | 0.0000 | 0.00 |
| BTC/USD | `7c39c7a2` | 111 | 100 | 100 | 0 | 250.09 | 250.00 | +0.09 | +0.04% | 0.09 | 1.00 | 341.5610 | 0.00 |
| ETH/USD | `7c4c4ff3` | 127 | 65 | 92 | 27 | 200.38 | 200.00 | +0.38 | +0.19% | 0.00 | 1.00 | 213.9008 | 0.00 |
| LINK/USD | `4a53be56` | 69 | 46 | 66 | 22 | 75.22 | 75.00 | +0.22 | +0.29% | 0.00 | 1.00 | 0.0000 | 0.00 |
| SOL/USD | `bbe339a0` | 68 | 39 | 44 | 6 | 75.02 | 75.00 | +0.02 | +0.03% | 0.00 | 1.00 | 0.0000 | 0.00 |
| HYPE/USDC | `e6df7221` | 54 | 39 | 49 | 10 | 50.00 | 50.00 | +0.00 | +0.00% | 0.00 | 1.00 | 0.0000 | 0.00 |
| XLM/USDC | `5d335c96` | 61 | 38 | 38 | 0 | 50.00 | 50.00 | +0.00 | +0.00% | 0.00 | 1.00 | 9.2204 | 0.00 |
| NEAR/USDC | `9f737e8f` | 44 | 35 | 35 | 0 | 50.00 | 50.00 | +0.00 | +0.00% | 0.00 | 1.00 | 0.0000 | 0.00 |
| RAVE/USD | `a0a82b8c` | 881 | 29 | 39 | 10 | 50.00 | 50.00 | +0.00 | +0.00% | 0.00 | 1.00 | 0.0000 | 0.00 |
| XRP/USD | `a873b457` | 96 | 15 | 22 | 10 | 75.38 | 75.00 | +0.38 | +0.51% | 0.00 | 1.00 | 0.0000 | 0.00 |
| RE/USD | `04e1cafc` | 48 | 15 | 20 | 5 | 51.65 | 50.00 | +1.65 | +3.30% | 0.00 | 1.00 | 0.0000 | 0.00 |
| PUMP/USD | `650df31a` | 32 | 14 | 23 | 9 | 50.96 | 50.00 | +0.96 | +1.92% | 0.00 | 1.00 | 0.0000 | 0.00 |
| HBAR/USDC | `7a4e0e88` | 20 | 10 | 12 | 2 | 50.14 | 50.00 | +0.14 | +0.28% | 0.00 | 1.00 | 0.0000 | 0.00 |
| AGLD/USD | `a632ff52` | 9 | 4 | 7 | 3 | 50.24 | 50.00 | +0.24 | +0.48% | 0.00 | 1.00 | 0.0000 | 0.00 |
| AERO/USDC | `cc18670d` | 12 | 2 | 3 | 1 | 25.17 | 25.00 | +0.17 | +0.69% | 0.00 | 1.00 | 0.0000 | 0.00 |
| ADA/USDC | `ff6a37a3` | 10 | 0 | 5 | 5 | 25.00 | 25.00 | +0.00 | +0.00% | 0.00 | 1.00 | 0.0000 | 0.00 |
| LTC/USDC | `934f242d` | 1 | 0 | 0 | 0 | 25.00 | 25.00 | +0.00 | +0.00% | 0.00 | 1.00 | 0.0000 | 0.00 |
| LSETH/USDC | `9f1b9bff` | 1 | 0 | 0 | 0 | 25.00 | 25.00 | +0.00 | +0.00% | 0.00 | 1.00 | 0.0000 | 0.00 |
| WLFI/USDC | `c0d9eb49` | 2 | 0 | 0 | 0 | 25.00 | 25.00 | +0.00 | +0.00% | 0.00 | 1.00 | 0.0000 | 0.00 |

## What stands out

**Growth is not merely capped, it is absent.** CHIP/USD closed 2,880
tranches and grew its target by $1.77 — roughly six hundredths of a cent
per fill. BILL/USD closed 2,443 for $3.10. If the intended behaviour were
"grow up to max_target_growth_pct per buy cycle", these figures would be
orders of magnitude larger.

**Nine bots have never grown at all**, including ZEC/USD at 412 closed
tranches and RAVE/USD at 29 — the operator's cited example. Whatever
produces the small growth on other bots does not fire for these, which
means the growth path is conditional on something not satisfied here.
That difference is the sharpest available lead: two populations, same
code.

**`fold_cycle_cap_consumed` is zero on 32 of 35 bots — but this does NOT
mean the cap never engaged.** Correction to an earlier reading of this
table: `scrumming_bot.py:7159-7161` resets that counter to 0.0 on every
SCRUM fire, so a zero means "no fold growth since the last scrum", not
"never grew". The column cannot support the stronger claim and it is
withdrawn. The $26.20 total above is unaffected — that is measured
directly as target minus anchor, not inferred from this counter.

**$565.88 is stranded in `pending_wire_credits`,** concentrated in
BTC/USD ($341.56) and ETH/USD ($213.90). Both hold tranches, which under
the confirmed absorb defect means the outlet is permanently closed.

## The freeze is a RULE, not a per-bot fault

Added 2026-08-06 after the operator challenged a bot-specific callout:
*"Always concerned about these bot-specific call outs. All bots have the
same settings for the most part."* Correct, and testing it produces the
sharpest statement in this document.

`max_target_growth_pct` is **1.0 on all 35 bots**. The settings are
uniform. The only per-bot variable feeding the cycle cap is the anchor,
and `cycle_cap = anchor x 1%`. The exchange minimum trade size is ~$1.00
(confirmed for ONDO/USD from the live log: `min_cost $1.00`).

| Anchor | Cycle cap | Bots | Can autonomously fold? |
|---|---|---:|---|
| $25 | $0.25 | 5 | **no** |
| $50 | $0.50 | 10 | **no** |
| $75 | $0.75 | 6 | **no** |
| $100 | $1.00 | 6 | yes |
| $125 | $1.25 | 1 | yes |
| $150 | $1.50 | 1 | yes |
| $200 | $2.00 | 3 | yes |
| $250 | $2.50 | 3 | yes |

**Any bot with a target balance below $100 cannot autonomously fold AS
CURRENTLY SIZED.**

*Corrected 2026-08-06 after operator input.* The original wording said
"can never fold", which overstates it. The freeze is a consequence of
per-tranche sizing meeting the cap filter, and BOTH inputs are about to
change: fold tranches within 0.1% are to be merged downward (mirroring
Stack Tranches), and wire credits legitimately inflate tranche `usd`
once routing is correct.

But neither of those lifts the freeze on its own, and this is the part
that is counter-intuitive. The cap filter admits a tranche only if it
fits ENTIRELY -- `if _running_usd + _t_usd <= _cap_remaining_for_queue`
-- and explicitly refuses to deploy part of one. So a LARGER tranche is
MORE likely to be refused whole. Merging and wire inflow both increase
tranche size, and therefore both make this specific failure worse until
the cap stops being used as a spending limit.

ETH/USD is the existing proof: all 27 of its tranches carry wire credit,
and all 27 exceed its cycle cap.

The freeze lifts when the CAPITAL budget is separated from the GROWTH
budget (audit Step 11 / decision D1). `anchor x max_growth_pct` is a
bound on how far the target may RISE, not on how much may be SPENT.
Deploying $5 of tranche capital to raise a $50 target by $0.50 is
exactly the configured 1% -- growth is measured against the anchor, not
against the deployment.
One percent of its anchor is smaller than the minimum trade size, so the
cap filter admits a set the exchange then refuses -- no admissible set
exists at any price. That is **21 of 35 bots**, holding 279 standing
tranches. The remaining 14 hold 647.

This reframes the operator's own example. RAVE/USD sits at anchor $50,
cap $0.50, and is in the frozen class. Nothing about RAVE is special; it
is one of twenty-one.

**What the rule does NOT explain.** ZEC/USD has a $150 anchor and a $1.50
cap, is not frozen by this rule, and still shows zero lifetime growth.
So the cap-versus-minimum deadlock accounts for many zero-growth bots but
not all of them, and a second mechanism remains unidentified for the
unfrozen ones.

**Reporting discipline this establishes.** Per-bot figures in this
remediation should be given as a distribution plus an explicit worst
case, never as a bare bot name. A callout like "CHIP/USD carries 199
tranches" reads as a claim about CHIP when the true statement is about
every bot above the anchor threshold, and CHIP merely holds the largest
queue.

## What this does NOT establish

- **It does not identify the broken line.** It proves the outcome is
  wrong; the code audit running alongside it establishes where.
- **It does not prove the small growth is compounding.** The $1.77 on
  CHIP may come from an unrelated writer of `target_balance`. Nothing
  here attributes it.
- **It does not establish what the growth SHOULD have been.** That needs
  the intended formula, which is a code question.
- **`tranches_closed_lifetime` is assumed to mean filled.** If it also
  counts cancelled or expired tranches, the fill count is lower than
  shown. Not yet verified against the writer.