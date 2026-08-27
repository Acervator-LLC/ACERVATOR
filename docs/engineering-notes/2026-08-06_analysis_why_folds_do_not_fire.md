# ANALYSIS — why folds do not fire, measured from the live diagnostics log

**Taken** 2026-08-06 from `~/.acervator_logs/trade/diagnostics.log`, read-only
**Window** 11,604 `bot_log` records, roughly 27 minutes of live running on v3.24.35
**Companion** `2026-08-06_measurement_tranche_compounding_fleet.md` (the state-side evidence)

---

## The instrument was verified first

A count of zero is a claim about the instrument, not the world. Before
reading anything into the absence of growth events, the log was checked
for what it *does* contain: 11,604 `category: "bot_log"` records, last
written 16:59 today, carrying `HOLD FOLD`, `FOLD_DIAG_BLOCKED`,
`BULLSEYE`, `TRADE NOTIFICATION` and others. The bus-to-disk path works.
The zeros below are real.

## The chain stops before compounding is ever reached

In this window:

| Marker | Count |
|---|---:|
| `HOLD FOLD` | 2,512 |
| `FOLD_DIAG_BLOCKED` | 216 |
| `FOLD REFUSED` | 19 |
| `TARGET GROWN` | **0** |
| `COMPOUND SKIPPED` | **0** |
| `TARGET-GROW HELD` | **0** |
| `FOLD CYCLE RESET` | **0** |

The compounding code at `scrumming_bot.py:1409` is not producing zero
growth. **It is not being reached at all.** Folds are held upstream of
it, so the surplus calculation, the growth cap and the standing-surplus
pool never run. This matches the operator's account exactly: the target
never changes, so the max-target-growth surplus cutoff is never fed.

## Tranches are ready and are refused

From the `FOLD_DIAG_BLOCKED` events, which state eligibility explicitly:

> **4,516 of 7,209 tranches (62.6%) were strict-eligible and were refused.**

**CORRECTION, 2026-08-06 (Phase 1 Step 2).** That figure is measured on
the WRONG PREDICATE and should not be relied on. The counter producing it
used `ticker.last < ref AND ticker.last <= initial_buy_price`, while the
executor that actually fires uses `ticker.last <= ref * _otd_factor` --
strict `<` versus `<=`, an `initial_buy_price` term the executor does not
have, and no OTD factor at all. So the count both over- and under-reports
relative to the gate it claims to describe, and the true figure is
unknown until the corrected instrument has run.

The qualitative finding survives: eligible tranches were being refused at
scale, and the log named the wrong blocker. The precise percentage does
not. The counter now shares one binding with the executor
(`test_fold_diag_matches_executor.py`), so the next reading will be
measured against the gate that fires.

This is the core fact. The tranches are not waiting for price. They have
already cleared their own price gates and are being turned away by the
fold gate stack.

Blocker frequency across 229 events (an event can carry several):

| Blocker | Events | Share |
|---|---:|---:|
| `TA-not-bearish` | 214 | 93% |
| `OTD-hyst` | 202 | 88% |
| `BB-above-lower-detect` | 160 | 70% |
| `fold_ok_midline=False` | 44 | 19% |

Most common exact combinations:

| Count | Combination |
|---:|---|
| 88 | `BB-above-lower-detect + OTD-hyst + TA-not-bearish` |
| 68 | `OTD-hyst + TA-not-bearish` |
| 33 | all four |

Folds must clear three to four independent gates simultaneously.

## Finding 1 — an undisclosed hardcoded confidence floor

`scrumming_bot.py:6372-6375`:

```python
is_bullish = (eff_direction in (SignalDirection.BULLISH, SignalDirection.NEUTRAL)
              and eff_confidence >= 0.25)
is_bearish = (eff_direction in (SignalDirection.BEARISH, SignalDirection.NEUTRAL)
              and eff_confidence >= 0.25)
```

`0.25` is a **hardcoded literal**. There is no config key for it anywhere
in `src/`, and no confidence field on any of the 35 live bots except
`detonation_confidence_min`, which belongs to a different subsystem.

The operator set `fold_require_ta_bearish = True`. The code enforces
*"TA bearish AND confidence ≥ 0.25"*. The second conjunct is invisible,
unconfigurable, and not implied by the setting's name. It is the top
blocker at 93% of refusals.

It is **symmetric**: line 6373 applies the same undisclosed floor to
`is_bullish`, so SCRUM firing is gated the same way.

**Status: CONFIRMED as present and undisclosed. NOT yet established as
wrong.** A confidence floor may be entirely correct. What is defective
is that it is unnamed, unconfigurable, and invisible in the logs.

## Finding 2 — the hold message names the wrong reason

`scrumming_bot.py:8455-8459`:

```python
elif self._fold_tranches and not is_bearish:
    self._bus.emit("bot.log", ...,
        message=f"HOLD FOLD: {len(self._fold_tranches)} tranche(s) "
                f"(${self._fold_queue_usd:.4f}) queued but "
                f"TA={eff_direction.name} — waiting for BEARISH")
```

It prints `eff_direction`, not the thing that actually failed. When
direction is BEARISH but confidence is below 0.25, it renders:

> `HOLD FOLD: 178 tranche(s) ($10.1001) queued but TA=BEARISH — waiting for BEARISH`

Waiting for the condition it reports as already met. **1,377 occurrences
in 27 minutes.** The operator has been reading a log that states the
opposite of the truth about their own fold gate. The same defect appears
in `FOLD_DIAG_BLOCKED` as `TA-not-bearish(dir=BEARISH)`.

This is a diagnostic-truth defect of the same family as C51 and NF-5:
the surface is confidently wrong rather than silent. It is almost
certainly why this gate was never suspected.

**Status: CONFIRMED. This one is unambiguously a defect** — the message
is false regardless of whether the floor itself is correct.

## What this does NOT establish

- **It does not establish that any gate is miscalibrated.** Four of
  them are operator-configured and switched on deliberately
  (`fold_require_ta_bearish`, `fold_hold_in_downtrend`,
  `fold_defer_to_htf`, `scrum_detect_pct=75`). They may be doing
  precisely what they were told. Whether 62.6% refusal is wrong is a
  strategy question, not a code question, and it is the operator's call.
- **It does not establish that the compounding code itself works.** It
  has not been reached in this window, so it is untested by this
  evidence. The `_pending_wire_credits` absorb defect and the
  `_standing_surplus_usd` no-decrement defect are separate, confirmed,
  and downstream of here.
- **27 minutes is a short window** on one build. It is enough to prove
  the gate stack refuses eligible tranches at scale; it is not enough to
  characterise behaviour across market regimes.
- **`OTD-hyst` was not investigated.** It is the second-most-frequent
  blocker at 88% and nothing here explains what it is or whether it is
  behaving. That is the largest unexamined item.
- **No fix is proposed here.** Changing any of these alters live buy
  timing on 35 real-money bots.

## The one thing safe to fix immediately

Finding 2. Making the hold message name the actual failing condition
changes no trading behaviour whatsoever — it only stops the platform
lying to the operator about why 4,516 eligible tranches were refused.
Everything else in this document needs a deliberate decision first.

## Reference

- `src/trading/scrumming_bot.py:6372-6375` — the hardcoded floor
- `src/trading/scrumming_bot.py:8455-8459` — the false hold message
- `src/trading/scrumming_bot.py:1385` — `[COMPOUND SKIPPED]`, never reached
- `src/trading/scrumming_bot.py:1409` — the target growth write, never reached
- `src/trading/scrumming_bot.py:7159-7161` — the cycle-cap reset on SCRUM fire
