# Target Balance growth family — three defects

Date: 2026-08-21
Referee: cold read of live code and live state
Trigger: operator report — "the compounding rate appears to stay frozen as a
calculation based on the starting value of the bot but this should refresh
after each Fold so as to induce the appropriate curve"

Two numbers carry every finding below.

- `_anchor_target_balance` — the operator input value. The Target Balance
  spinbox shows it. Persistence stores it as `config.target_balance`.
- `_target_balance` — the value the bot trades against. Fold surplus grows it.

`_target_balance` minus `_anchor_target_balance` is accrued growth.

## Measured fleet state

Source: `~/.acervator/bot_state.json`, read only, 38 bots.

| pair | anchor | target | accrued | cap per Fold |
|---|---|---|---|---|
| IMU | $50.00 | $63.53 | +27.1% | $0.50 |
| CHIP | $250.00 | $258.68 | +3.5% | $2.50 |
| BILL | $300.00 | $307.65 | +2.6% | $3.00 |
| ALLO | $125.00 | $132.44 | +6.0% | $1.25 |
| BICO | $50.00 | $55.95 | +11.9% | $0.50 |
| CAP | $50.00 | $55.41 | +10.8% | $0.50 |

Fleet: anchor $3,500.00 grew to $3,585.50. Accrued $85.50, or 2.44%.
Parked surplus $14.35. Every bot runs `max_target_growth_pct = 1.0`.

## Defect 1 — a top-up destroys accrued growth

Status: FIXED in v3.25.9. Re-verified 2026-08-24 by cold read.
`set_target_balance_live` now compares against the anchor. The method
docstring carries the IMU worked example below. This section is kept as
the record of the defect, not as an open item.

`set_target_balance_live` at `src/trading/scrumming_bot.py:1571` reads:

    if nt > old_t and accrued > 1e-9:

`old_t` is `_target_balance`, the grown value. `nt` arrives from a spinbox
that displays the anchor. The two sides use different references.

IMU shows $50.00 and trades against $63.53. Raise the displayed value to
$60.00 and the code evaluates `60 > 63.53` as false. The else branch sets
target and anchor both to $60.00. The bot loses $13.53 of accrued growth and
the target falls by $3.53. The position now sits above target, the Delta
turns positive, and the bot folds the excess. The growth gets sold.

Any top-up smaller than accrued growth does this. Six live bots qualify.

The GUI documents the reference split at `src/gui/bot_live_settings.py:3736`.
The spinbox keeps showing the anchor on purpose, because a spinbox holding
the grown value would register an edit on every panel open. The comparison
never got aligned to that decision.

Repair: compare against `old_a`. The spinbox is anchor denominated, so the
comparison must be too. A withdrawal below the anchor still clears growth,
which matches the 2026-07-26 directive.

## Defect 2 — the growth cap never compounds

Status: LIVE, re-verified 2026-08-24. Tracked as a GitHub issue.
Four sites still read the anchor, not three: `scrumming_bot.py` lines
1858, 2107, 10131 and 10423. Fleet re-measured the same day: 35 of 38
bots carry accrued growth, $92.24 fleet-wide, $13.37 parked behind the
frozen cap. IMU is +27.1% and still caps each Fold at $0.50.

Three sites compute the per-cycle growth cap from the anchor:

- `src/trading/scrumming_bot.py:1702` applies the growth
- `src/trading/scrumming_bot.py:1951` sizes the preview
- `src/trading/scrumming_bot.py:9850` admits the eligibility queue

Each reads `self._anchor_target_balance * (_cap_pct / 100.0)`. The anchor
moves only on operator input, wire income, or tranche arrival. A Fold never
moves it. The cap therefore holds one fixed dollar value for the life of the
bot.

IMU has grown 27.1% and still caps each Fold at $0.50, the same $0.50 it
carried at $50.00. A compounding cap would read $0.6353 today.

The curve is `anchor x (1 + 0.01N)`, not `anchor x 1.01^N`. Projected from a
$50.00 bot at 1% per Fold:

| Folds | frozen | compounding | difference |
|---|---|---|---|
| 27 | $63.50 | $65.41 | $1.91 |
| 100 | $100.00 | $135.24 | $35.24 |
| 200 | $150.00 | $365.80 | $215.80 |

The cap already holds money back. `standing_surplus_usd` collects profit that
exceeded the cap. CAP holds $7.79 against a $0.50 cap, which is fifteen
Folds of growth waiting behind a frozen number. The fleet holds $14.35.

Coupled consumer: `src/gui/main_window.py:1314` draws the ceiling line at
`anchor_px x (1 + cap_pct/100)`. Enforcement at
`src/trading/scrumming_bot.py:11932` uses `_target_balance` instead. The
drawn line and the enforced line already disagree. On IMU the chart shows
$50.50 where the bot enforces $64.17. Any cap change must land this too.

Constraint to honour: MEM-249 at `src/trading/bot_container.py:2206` states
that fold surplus is the only legitimate mechanism that may grow the target,
bounded per event. Changing the base of the bound keeps that rule intact.

## Defect 3 — detonation can fire twice on one bull run

Status: DORMANT. Operator deferred the repair on 2026-08-21.

`_check_detonation_trigger` fires on the edge into BULLISH at confidence
0.75 or above. `_detonation_last_signal_bullish` holds the edge state. The
attribute initialises to False at `src/trading/scrumming_bot.py:681` and no
save path writes it. `_detonation_last_check_ts` behaves the same way.

A restart clears both. A daily candle that stays bullish reads as a fresh
crossing, and the bot detonates again. The operator directive says the bot
detonates once, not every hour. The code honours that inside one process and
breaks across restarts.

`_execute_detonation` also measures the position from `_current_holdings`
rather than the exchange. On BILL that reads 14,131 units against 15,778 in
the wallet.

Evidence that it has never fired: every log under `~/.acervator_logs` was
searched for detonation events. The search returned three config dumps
showing `detonation_enabled: False` and no trigger or execution line.
`detonation_enabled` reads False on all 38 bots and the declared default at
`src/trading/bot_container.py:412` is False.

Precondition recorded: repair this before enabling detonation on any bot.

## Ruled out

The operator asked whether Clear Tranches or Clear Wire Credits caused the
reset. Neither does. `_target_balance` takes an assignment in eight places:
bot construction, the two operator-change branches, Fold growth, wire income,
tranche arrival, state restore, and the detonation reset. `clear_fold_tranches`
states the exclusion in its own docstring, and `clear_pending_wire_credits`
assigns neither number.

## Order of repair

1. Defect 1. It destroys money now and needs one line.
2. Defect 2, with the chart consumer.
3. Defect 3, held until the operator enables detonation.
