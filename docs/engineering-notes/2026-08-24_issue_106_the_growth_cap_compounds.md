# Issue #106 — the per-Fold growth cap compounds

Date: 2026-08-24
Unit: `fix-106-growth-cap-compounds`
Instrument: `tools/sweep_the_growth_cap.py`

Operator report, 2026-08-21: "the compounding rate appears to stay frozen
as a calculation based on the starting value of the bot but this should
refresh after each Fold so as to induce the appropriate curve."

## The mechanism

`_anchor_target_balance` is the operator's input value. It moves on
operator input, on wire income and on tranche arrival. A Fold never
moves it. `_target_balance` is the number the bot trades against, and
fold surplus grows it.

Every site that needed the per-cycle Growth Rate Cap spelled it out for
itself as `_anchor_target_balance * (max_target_growth_pct / 100)`. The
cap therefore held one fixed dollar value for the life of the bot. The
curve was `anchor x (1 + 0.01N)` where the operator asked for `1.01^N`.

The repair adds ONE property, `ScrummingBot.cycle_growth_cap_usd`, and
every site reads it.

## The audit's site list was WRONG, in both directions

The 2026-08-21 audit named three sites. Issue #106 named four and said
the audit had missed one. The true count is EIGHT.

| # | site | role | named before? |
|---|---|---|---|
| A | `scrumming_bot.py` `_apply_fold_target_growth` | ENFORCES the growth | audit + issue |
| B | `scrumming_bot.py` `_preview_fold_growth` | sizes the preview | audit + issue |
| C | `scrumming_bot.py` `tick()` eligibility queue | admits tranches | audit + issue |
| D | `scrumming_bot.py` `tick()` `FOLD_DIAG_SURPLUS_CHECK` | DIAGNOSTIC ONLY | issue only |
| E | `bot_container.py` `get_status` over-cap summary | status readout | **NEITHER** |
| F | `bot_container.py` `get_status` `cycle_growth_budget_usd` | GUI export | **NEITHER** |
| G | `bot_live_settings.py` "Cycle growth budget" row | GUI row | **NEITHER** |
| H | `main_window.py` chart ceiling line | chart overlay | issue only |

D is not an enforcement site and the issue implies it is. Nothing
downstream reads its `_cycle_cap_growth`; the drain delegates to A,
which reads the cap itself. D only prints. It still had to move,
because it is the line an operator greps to see what the budget was.

E, F and G were missed by both. F is the number the GUI SHOWS as the
cycle growth budget. It had disagreed with enforcement from the moment
any bot first compounded.

## Three sites use the same formula and are NOT the growth cap

`scrumming_bot.py` also computes `anchor * (pct/100)` in three places as
a POSITION budget — headroom above target on a buy path, not a bound on
target growth.

* `_pre_buy_allowed`, MEM-253 Layer 1 — reached only on `path="unspecified"`.
* `_execute_buy`, MEM-251 v2 Layer 1 — reached only on `path="unspecified"`.
* the MEM-253 fold-branch probe in `tick()` — assigned and **never read**.

None was changed. The coherence question was asked and answered: the
fold paths (`fold_rebuy`, `manual_tranche_fire`) do not consult them at
all — Layer 1 gives those paths `float(cost)` and `_projected + 1.0`
respectively — so a fold-back that the widened cap now admits cannot be
refused by a frozen buy budget. Changing them would widen BUY permission
with no operator report behind it.

## The base is the CYCLE-OPEN target, not the raw target

`_apply_fold_target_growth` adds the same `_growth_applied` to
`_target_balance` and to `_fold_cycle_cap_consumed`. Their difference is
therefore invariant across a cycle and equals the target as it stood
when the cycle opened.

Reading the RAW target would let the cap grow as the cycle spent it. One
cycle would settle at the fixed point `c = target0 * pct / (1 - pct)`,
which at the 1.0% default is $1.0101 on a $100 target — an overrun of
the per-event bound MEM-249 states, by 1.01%. Measured through the real
applier: `101.01010100999994` against an expected `101.00`.

Subtracting the consumption pins the base for the cycle. It needs no new
attribute, no persistence field and no state migration.

## Direction

`cap_after - cap_before = (target - consumed - anchor) * pct/100`.

The cap widens exactly when accrued growth is at least the consumption
booked this cycle. Every dollar of this cycle's consumption was added to
the target by the same line that booked it, so accrued growth contains
it and the difference cannot be negative.

Two states break the containment, both named in the property's
docstring: `_execute_detonation` puts the target back to the anchor and
deliberately does NOT clear `_fold_cycle_cap_consumed`, and a withdrawal
below the anchor clears growth the same way. In both the base sits below
the anchor until the cycle resets. Both are bounded by consumption
already booked, both self-clear on the next reset, and
`detonation_enabled` is False on all 38 live bots.

Measured over 228 rows: 210 wider, 18 identical, **0 narrower**.

## What did not change

MEM-249 is intact. Fold surplus is still the only mechanism that may
grow the target, and it is still bounded per event. Only the BASE of the
bound moved. `TestMEM249StillHolds` pins it.

## Measured

`tools/sweep_the_growth_cap.py` runs the sweep. It pairs each of the
operator's 38 live bots with the Stone Tablet for that bot's own asset
and replays six tape lengths — 35, 40, 60, 100, 200 and 400 bars — for
**228 rows**. No bot was skipped for a missing tablet. The fleet anchor
is $3,501.51 against a target of $3,593.75, $13.37 parked, and every bot
runs the 1.0 % cap.

* fleet per-cycle cap **$35.0151 -> $35.9301** (+2.61%)
* IMU **$0.5000 -> $0.6353**; CAP's budget **$0.0000 -> $0.0491**, which
  releases the first of the $7.79 it has parked
* 30 of 222 ladder rows change which tranches the production packer
  takes; 204 deploy more, **0 deploy less**, **$+5.4799** of fold-back
  deployed across the fleet
* over a 400-bar tape (median 17 D2-b cycles) the fleet target after N
  cycles is **$4,182.26 frozen vs $4,250.35 compounding**

The trajectory widens with the tape, which is the curve the operator
asked for.

| bars | median cycles | fleet target, frozen | compounding | difference |
|---|---|---|---|---|
| 35 | 0 | $3,599.50 | $3,599.79 | $+0.29 |
| 40 | 0 | $3,606.00 | $3,606.42 | $+0.42 |
| 60 | 1 | $3,633.50 | $3,635.15 | $+1.65 |
| 100 | 3 | $3,703.28 | $3,707.76 | $+4.47 |
| 200 | 8 | $3,859.09 | $3,875.74 | $+16.64 |
| 400 | 17 | $4,182.26 | $4,250.35 | $+68.09 |

## The controls that make the zeros above readable

Six ran, and all six passed.

The reader is not blind: 38 bots declared in state, 38 read, 35 already
carrying `target != anchor`, 37 carrying a queued tranche ladder, 406
tablets read.

The decision instrument is the production packer, not a model of it.
`_plan_fold_consumption` touches **zero** `self` attributes — asserted by
walking the shipping file's syntax tree — so the sweep calls it unbound
and every admission verdict below is the shipping method's.

Both positive controls inject a known perturbation and count what moves.

| injected into the cap percentage | rows whose cap moves |
|---|---|
| 0 | 0 |
| 1e-12 | 228 |
| 0.01 | 228 |

| injected into the packer's budget (USD) | admission verdicts that move |
|---|---|
| 0 | 0 |
| 1e-09 | 6 |
| 0.1 | 60 |
| 100 | 222 |

The packer is a step function, so a small injection moving nothing is
correct behaviour rather than a dead instrument; the last row proves it
is alive. The **0 narrower** count above is believable only because
these two lines are not zero.

The no-op control is the other half. 18 rows carry no accrued growth and
no consumption, so `target == anchor` and the new base IS the anchor. The
cap changed on **0** of them.

## Timing note for the operator

The change is one-directional and small on the first cycle: +$0.9150
across the whole fleet, +2.61%. It compounds from there. The live test
now running is not disturbed on its first fold — the largest single-bot
first-cycle change is IMU at +$0.1353.
